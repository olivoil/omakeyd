from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omakeyd import core


YOGA_MAIN = """[ids]
# AT Translated Set 2 keyboard (the built-in laptop keyboard).
0001:0001:09b4e68d

[main]
e = f
r = p
t = b
y = j
u = l
i = u
o = y
p = ;
s = r
d = s
f = t
h = m
j = n
k = e
l = i
; = o
v = d
b = v
n = k
m = h
"""


class FakeRunner:
    def __init__(self, returncode: int = 0, stdout: str = '{"ok":true}\n', stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.commands: list[list[str]] = []

    def __call__(self, command):
        self.commands.append(list(command))
        return core.CommandResult(self.returncode, self.stdout, self.stderr)


def load_script(name: str, path: Path):
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OmakeydCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.keyd = self.root / "keyd"
        self.keyd.mkdir()
        self.config = self.root / "config.json"
        self.runtime_helper = self.root / "omakeyd-helper"
        self.runtime_helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.runtime_helper.chmod(0o755)
        self.environment = patch.dict(
            os.environ,
            {
                "OMAKEYD_CONFIG": str(self.config),
                "OMAKEYD_KEYD_DIR": str(self.keyd),
                "OMAKEYD_HELPER": str(self.runtime_helper),
                "OMAKEYD_PKEXEC": "/usr/bin/pkexec",
            },
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def write_profile(self, content: str = YOGA_MAIN) -> Path:
        path = self.keyd / "laptop-colemak-dh.conf"
        path.write_text(content, encoding="utf-8")
        return path

    def managed_profile(self, rows=core.COLEMAK_DH_YOGA_ROWS) -> str:
        values = core.normalized_flat_rows(rows)
        layer = "omakeyd_laptop_colemak_dh"
        bindings = "\n".join(
            f"{source} = {target}"
            for source, target in zip(core.PRIMARY_KEYS, values)
        )
        return (
            YOGA_MAIN
            + f"\n[global]\ndefault_layout = {layer}\n\n"
            + core.MANAGED_BEGIN
            + f"\n[{layer}:layout]\n{bindings}\n"
            + core.MANAGED_END
            + "\n"
        )

    def test_detects_the_existing_yoga_keyd_mapping(self) -> None:
        profile = core.parse_keyd_profile(self.write_profile())
        self.assertIsNotNone(profile)
        self.assertEqual(profile["label"], "Built-in keyboard")
        self.assertEqual(profile["baseRows"], [list(row) for row in core.COLEMAK_DH_YOGA_ROWS])
        self.assertEqual(profile["currentRows"], [list(row) for row in core.COLEMAK_DH_YOGA_ROWS])
        self.assertFalse(profile["ready"])

        layout = core._detected_layout(profile["currentRows"], profile["label"])
        self.assertEqual(layout["name"], "Colemak-DH")

    def test_snapshot_is_profile_first_and_has_no_hyprland_devices(self) -> None:
        self.write_profile()
        payload = core.snapshot(path=self.config, keyd_dir=self.keyd)
        self.assertEqual(payload["selectedProfile"], "laptop-colemak-dh")
        self.assertEqual([item["id"] for item in payload["profiles"]], ["laptop-colemak-dh"])
        self.assertEqual(
            [item["id"] for item in payload["layouts"]],
            ["qwerty", "colemak-dh-yoga"],
        )
        self.assertNotIn("keyboards", payload)
        self.assertNotIn("catalog", payload)
        self.assertEqual(payload["profiles"][0]["currentLayoutId"], "colemak-dh-yoga")

    def test_managed_profile_is_ready_and_tracks_its_actual_rows(self) -> None:
        self.write_profile(self.managed_profile(core.DISPLAY_ROWS))
        payload = core.snapshot(path=self.config, keyd_dir=self.keyd)
        profile = payload["profiles"][0]
        self.assertTrue(profile["ready"])
        self.assertTrue(profile["canApply"])
        self.assertEqual(profile["currentLayoutId"], "qwerty")
        self.assertEqual(profile["currentName"], "QWERTY (US)")

    def test_snapshot_honors_the_pkexec_override_when_path_lookup_fails(self) -> None:
        self.write_profile(self.managed_profile(core.DISPLAY_ROWS))
        with patch("omakeyd.core.shutil.which", return_value=None):
            payload = core.snapshot(path=self.config, keyd_dir=self.keyd)

        self.assertTrue(payload["helper"]["pkexecAvailable"])
        self.assertTrue(payload["profiles"][0]["canApply"])

    def test_layout_must_be_a_complete_permutation(self) -> None:
        rows = [list(row) for row in core.DISPLAY_ROWS]
        rows[0][1] = "q"
        with self.assertRaisesRegex(core.OmakeydError, "exactly once") as raised:
            core.validate_rows(rows)
        self.assertIn("Missing: w", raised.exception.detail)
        self.assertIn("Repeated: q", raised.exception.detail)

    def test_saves_visual_layout_rows_without_creating_xkb_files(self) -> None:
        result = core.save_layout(
            "Colemak-DH Copy",
            "dh",
            "q w f p b j l u y ;",
            "a r s t g m n e i o",
            "z x c d v k h , . /",
            path=self.config,
        )
        self.assertEqual(result["layout"]["brief"], "DH")
        saved = core.load_config(self.config)["layouts"]["colemak-dh-copy"]
        self.assertEqual(saved["rows"], [list(row) for row in core.COLEMAK_DH_YOGA_ROWS])
        self.assertEqual(list(self.root.glob("**/xkb/**")), [])

    def test_apply_calls_only_the_constrained_helper_and_persists_after_success(self) -> None:
        self.write_profile(self.managed_profile())
        runner = FakeRunner()
        result = core.apply_layout(
            "laptop-colemak-dh",
            "qwerty",
            runner,
            self.config,
            self.keyd,
        )
        self.assertEqual(result["layout"], "qwerty")
        command = runner.commands[0]
        self.assertEqual(command[:5], [
            "/usr/bin/pkexec",
            str(self.runtime_helper),
            "apply",
            "--profile",
            "laptop-colemak-dh",
        ])
        self.assertEqual(command[5], "--rows")
        self.assertEqual(len(command[6].split(",")), 30)
        saved = core.load_config(self.config)
        self.assertEqual(saved["profiles"]["laptop-colemak-dh"]["lastLayout"], "qwerty")

    def test_failed_apply_does_not_persist_requested_layout(self) -> None:
        self.write_profile(self.managed_profile())
        runner = FakeRunner(1, '{"ok":false,"error":{"message":"no"}}\n')
        with self.assertRaisesRegex(core.OmakeydError, "was not applied"):
            core.apply_layout(
                "laptop-colemak-dh",
                "qwerty",
                runner,
                self.config,
                self.keyd,
            )
        saved = core.load_config(self.config)
        self.assertNotIn("laptop-colemak-dh", saved["profiles"])

    def test_ready_profile_can_reinstall_a_missing_runtime_helper(self) -> None:
        self.write_profile(self.managed_profile())
        self.runtime_helper.unlink()
        state = core.snapshot(path=self.config, keyd_dir=self.keyd)
        self.assertTrue(state["profiles"][0]["ready"])
        self.assertTrue(state["profiles"][0]["needsSetup"])
        runner = FakeRunner()
        result = core.setup_profile(
            "laptop-colemak-dh",
            runner,
            self.config,
        )
        self.assertIn("Reinstalled", result["message"])
        self.assertIn("--install-only", runner.commands[0])

    def test_v1_configuration_migrates_custom_rows(self) -> None:
        old = {
            "version": 1,
            "selectedDevice": "keyd-virtual-keyboard",
            "favorites": [],
            "devices": {},
            "customLayouts": {
                "my_layout": {
                    "name": "My layout",
                    "brief": "MY",
                    "rows": [list(row) for row in core.DISPLAY_ROWS],
                }
            },
        }
        self.config.write_text(json.dumps(old), encoding="utf-8")
        migrated = core.load_config(self.config)
        self.assertEqual(migrated["version"], 2)
        self.assertIn("my-layout", migrated["layouts"])
        self.assertEqual(json.loads(self.config.read_text())["version"], 2)

    def test_setup_transform_preserves_current_mapping_in_managed_layer(self) -> None:
        setup_module = load_script("omakeyd_setup", core.PLUGIN_ROOT / "helper" / "omakeyd-setup")
        migrated, layer = setup_module.migrated_text("laptop-colemak-dh", YOGA_MAIN)
        path = self.write_profile(migrated)
        profile = core.parse_keyd_profile(path)
        self.assertEqual(layer, "omakeyd_laptop_colemak_dh")
        self.assertTrue(profile["ready"])
        self.assertEqual(profile["currentRows"], [list(row) for row in core.COLEMAK_DH_YOGA_ROWS])

    @unittest.skipUnless(shutil.which("keyd"), "keyd is not installed")
    def test_setup_transform_passes_the_installed_keyd_parser(self) -> None:
        setup_module = load_script("omakeyd_setup_keyd_check", core.PLUGIN_ROOT / "helper" / "omakeyd-setup")
        migrated, _ = setup_module.migrated_text("laptop-colemak-dh", YOGA_MAIN)
        staged = self.root / "staged.conf"
        staged.write_text(migrated, encoding="utf-8")
        result = subprocess.run(
            ["keyd", "check", str(staged)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_setup_refuses_an_existing_layout_switcher(self) -> None:
        setup_module = load_script("omakeyd_setup_refusal", core.PLUGIN_ROOT / "helper" / "omakeyd-setup")
        with self.assertRaisesRegex(setup_module.SetupError, "manual migration"):
            setup_module.migrated_text(
                "complex",
                "[ids]\n*\n[main]\ncapslock = setlayout(dvorak)\n[dvorak:layout]\na=b\n",
            )

    def test_runtime_helper_replaces_only_the_marked_block(self) -> None:
        helper_module = load_script("omakeyd_runtime_helper", core.PLUGIN_ROOT / "helper" / "omakeyd-helper")
        original = self.managed_profile()
        qwerty = list(core.PRIMARY_KEYS)
        updated = helper_module.replaced_text(
            original,
            "omakeyd_laptop_colemak_dh",
            qwerty,
        )
        self.assertEqual(updated.split(core.MANAGED_BEGIN)[0], original.split(core.MANAGED_BEGIN)[0])
        self.assertIn("e = e", updated.split(core.MANAGED_BEGIN)[1])
        self.assertIn("[main]\ne = f", updated)
        with self.assertRaisesRegex(helper_module.HelperError, "complete"):
            helper_module.parse_rows("q,w,e")

    def test_runtime_helper_restarts_and_checks_keyd(self) -> None:
        helper_module = load_script("omakeyd_runtime_restart", core.PLUGIN_ROOT / "helper" / "omakeyd-helper")
        calls = []

        def fake_systemctl(command):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.object(helper_module, "systemctl", side_effect=fake_systemctl):
            helper_module.restart_keyd(stability_seconds=0)

        self.assertEqual(calls, [["restart"], ["is-active", "--quiet"]])

    def test_snapshot_does_not_claim_a_layout_is_active_when_keyd_is_down(self) -> None:
        self.write_profile(self.managed_profile(core.DISPLAY_ROWS))
        payload = core.snapshot(path=self.config, keyd_dir=self.keyd, keyd_active=False)
        profile = payload["profiles"][0]
        self.assertFalse(payload["keydActive"])
        self.assertEqual(profile["configuredLayoutId"], "qwerty")
        self.assertEqual(profile["currentLayoutId"], "")
        self.assertEqual(profile["currentName"], "keyd is not running")

    def test_latest_keyd_crash_uses_only_a_keyd_core(self) -> None:
        runner = FakeRunner(
            stdout='[{"pid":1071,"sig":11,"exe":"/usr/bin/keyd"}]\n'
        )
        crash = core._latest_keyd_crash(runner)
        self.assertEqual(crash, {
            "pid": 1071,
            "process": "keyd",
            "executable": "/usr/bin/keyd",
            "signal": "SIGSEGV",
        })

    @unittest.skipUnless(shutil.which("keyd"), "keyd is not installed")
    def test_runtime_qwerty_block_passes_the_installed_keyd_parser(self) -> None:
        helper_module = load_script("omakeyd_runtime_keyd_check", core.PLUGIN_ROOT / "helper" / "omakeyd-helper")
        updated = helper_module.replaced_text(
            self.managed_profile(),
            "omakeyd_laptop_colemak_dh",
            list(core.PRIMARY_KEYS),
        )
        staged = self.root / "runtime-qwerty.conf"
        staged.write_text(updated, encoding="utf-8")
        result = subprocess.run(
            ["keyd", "check", str(staged)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
