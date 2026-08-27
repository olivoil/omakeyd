from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omakeyd import core


def keyboard(
    name: str = "at-translated-set-2-keyboard",
    active_keymap: str = "English (US)",
    active_layout_index: int = 0,
    layout: str = "us",
    variant: str = "",
) -> dict:
    return {
        "name": name,
        "active_keymap": active_keymap,
        "active_layout_index": active_layout_index,
        "layout": layout,
        "variant": variant,
    }


class FakeHyprRunner:
    def __init__(self, keyboards=None, keyd_active: bool = False, fail_switch: bool = False):
        self.keyboards = keyboards or [keyboard()]
        self.keyd_active = keyd_active
        self.fail_switch = fail_switch
        self.commands: list[list[str]] = []

    def __call__(self, command):
        command = list(command)
        self.commands.append(command)
        if command[:3] == ["systemctl", "is-active", "keyd.service"]:
            return core.CommandResult(
                0 if self.keyd_active else 3,
                "active\n" if self.keyd_active else "inactive\n",
                "",
            )
        if command[:3] == ["hyprctl", "-j", "devices"]:
            return core.CommandResult(0, json.dumps({"keyboards": self.keyboards}), "")
        if command[:2] == ["xkbcli", "compile-keymap"]:
            return core.CommandResult(0, "xkb_keymap {}\n", "")
        if command[:2] == ["xkbcli", "--version"]:
            return core.CommandResult(0, "xkbcli 1.0\n", "")
        if command[:2] == ["hyprctl", "eval"]:
            match = next(item for item in self.keyboards if item["name"] in command[2])
            layout_match = command[2].split('kb_layout = "', 1)[1].split('"', 1)[0]
            variant_match = command[2].split('kb_variant = "', 1)[1].split('"', 1)[0]
            match["layout"] = layout_match
            match["variant"] = variant_match
            match["active_layout_index"] = 0
            match["active_keymap"] = "English (US)"
            return core.CommandResult(0, "ok\n", "")
        if command[:2] == ["hyprctl", "switchxkblayout"]:
            if self.fail_switch:
                self.fail_switch = False
                return core.CommandResult(1, "", "switch failed")
            match = next(item for item in self.keyboards if item["name"] == command[2])
            index = int(command[3])
            match["active_layout_index"] = index
            match["active_keymap"] = "English (US)" if index == 0 else "Colemak-DH"
            return core.CommandResult(0, "ok\n", "")
        return core.CommandResult(1, "", "unexpected command")


class OmakeydCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = self.root / "config.json"
        self.xkb = self.root / "xkb" / "symbols"
        self.environment = patch.dict(
            os.environ,
            {
                "OMAKEYD_CONFIG": str(self.config),
                "OMAKEYD_XKB_DIR": str(self.xkb),
            },
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def test_layout_must_be_a_complete_permutation(self) -> None:
        rows = [list(row) for row in core.DISPLAY_ROWS]
        rows[0][1] = "q"
        with self.assertRaisesRegex(core.OmakeydError, "exactly once") as raised:
            core.validate_rows(rows)
        self.assertIn("Missing: w", raised.exception.detail)
        self.assertIn("Repeated: q", raised.exception.detail)

    def test_snapshot_discovers_only_typing_keyboards(self) -> None:
        runner = FakeHyprRunner(
            [
                keyboard(),
                keyboard("ideapad-extra-buttons"),
                keyboard("power-button"),
                keyboard("hl-virtual-keyboard-fcitx5"),
                keyboard("keyd-virtual-keyboard"),
                keyboard("zsa-technology-labs-voyager"),
            ]
        )
        payload = core.snapshot(runner=runner, path=self.config)
        self.assertEqual(
            [profile["id"] for profile in payload["profiles"]],
            ["at-translated-set-2-keyboard", "zsa-technology-labs-voyager"],
        )
        self.assertEqual(payload["profiles"][0]["label"], "Built-in keyboard")
        self.assertEqual(payload["selectedProfile"], "at-translated-set-2-keyboard")

    def test_snapshot_recognizes_the_exact_colemak_dh_mapping(self) -> None:
        layout = core._runtime_layout_name(core._builtin_layouts()[1])
        runner = FakeHyprRunner(
            [keyboard("at-translated-set-2-keyboard", "Colemak-DH", 1, f"us,{layout}", ",")]
        )
        payload = core.snapshot(runner=runner, path=self.config)
        profile = payload["profiles"][0]
        self.assertEqual(profile["currentLayoutId"], "colemak-dh")
        self.assertEqual(profile["currentBrief"], "DH")

    def test_v2_migration_renames_yoga_and_transfers_it_to_the_keyboard(self) -> None:
        self.config.write_text(
            json.dumps(
                {
                    "version": 2,
                    "selectedProfile": "laptop-colemak-dh",
                    "profiles": {"laptop-colemak-dh": {"lastLayout": "colemak-dh-yoga"}},
                    "layouts": {},
                }
            ),
            encoding="utf-8",
        )
        core.snapshot(runner=FakeHyprRunner(), path=self.config)
        migrated = core.load_config(self.config)
        self.assertEqual(migrated["version"], 3)
        self.assertEqual(migrated["selectedProfile"], "at-translated-set-2-keyboard")
        self.assertEqual(
            migrated["profiles"]["at-translated-set-2-keyboard"]["lastLayout"],
            "colemak-dh",
        )

    def test_saves_visual_layout_rows(self) -> None:
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
        self.assertEqual(saved["rows"], [list(row) for row in core.COLEMAK_DH_ROWS])

    def test_generated_xkb_keeps_z_on_ab01_and_does_not_touch_lsgt(self) -> None:
        layout = core._builtin_layouts()[1]
        content = core._xkb_content(layout)
        self.assertIn('include "us(basic)"', content)
        self.assertIn('key <AB01> { type[Group1] = "ALPHABETIC", [ z, Z ] };', content)
        self.assertNotIn("<LSGT>", content)
        self.assertIn("[ semicolon, colon ]", content)

    @unittest.skipUnless(shutil.which("xkbcli"), "xkbcli is not installed")
    def test_generated_colemak_dh_compiles_with_xkbcommon(self) -> None:
        target = self.xkb / core._runtime_layout_name(core._builtin_layouts()[1])
        core.atomic_write_text(target, core._xkb_content(core._builtin_layouts()[1]), 0o644)
        result = subprocess.run(
            [
                "xkbcli",
                "compile-keymap",
                "--include",
                str(self.root / "xkb"),
                "--include-defaults",
                "--layout",
                target.name,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_apply_uses_only_unprivileged_hyprland_and_xkb_commands(self) -> None:
        runner = FakeHyprRunner()
        result = core.apply_layout(
            "at-translated-set-2-keyboard", "colemak-dh", runner, self.config
        )
        self.assertEqual(result["layout"], "colemak-dh")
        commands = [command[0] for command in runner.commands]
        self.assertNotIn("pkexec", commands)
        self.assertNotIn("sudo", commands)
        self.assertIn(["hyprctl", "switchxkblayout", "at-translated-set-2-keyboard", "1"], runner.commands)
        eval_command = next(command for command in runner.commands if command[:2] == ["hyprctl", "eval"])
        self.assertIn("hl.device", eval_command[2])
        self.assertIn("kb_layout", eval_command[2])
        saved = core.load_config(self.config)
        self.assertEqual(
            saved["profiles"]["at-translated-set-2-keyboard"]["lastLayout"],
            "colemak-dh",
        )
        self.assertEqual(
            saved["profiles"]["at-translated-set-2-keyboard"]["baseline"],
            {"layouts": "us", "variants": "", "index": 0},
        )

    def test_reset_restores_the_pre_omakeyd_device_settings(self) -> None:
        runner = FakeHyprRunner()
        core.apply_layout(
            "at-translated-set-2-keyboard", "colemak-dh", runner, self.config
        )
        result = core.reset_layouts(runner, self.config)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reset"], ["at-translated-set-2-keyboard"])
        self.assertEqual(runner.keyboards[0]["layout"], "us")
        self.assertEqual(runner.keyboards[0]["active_layout_index"], 0)

    def test_failed_switch_rolls_back_and_does_not_persist(self) -> None:
        runner = FakeHyprRunner(fail_switch=True)
        with self.assertRaisesRegex(core.OmakeydError, "did not switch"):
            core.apply_layout(
                "at-translated-set-2-keyboard", "colemak-dh", runner, self.config
            )
        self.assertGreaterEqual(
            len([command for command in runner.commands if command[:2] == ["hyprctl", "eval"]]),
            2,
        )
        self.assertNotIn(
            "at-translated-set-2-keyboard", core.load_config(self.config)["profiles"]
        )

    def test_keyd_conflict_is_visible_and_blocks_apply(self) -> None:
        runner = FakeHyprRunner(keyd_active=True)
        payload = core.snapshot(runner=runner, path=self.config)
        self.assertTrue(payload["keydConflict"])
        self.assertFalse(payload["profiles"][0]["canApply"])
        with self.assertRaisesRegex(core.OmakeydError, "keyd is running"):
            core.apply_layout(
                "at-translated-set-2-keyboard", "colemak-dh", runner, self.config
            )
        self.assertFalse(any(command[:2] == ["hyprctl", "eval"] for command in runner.commands))


if __name__ == "__main__":
    unittest.main()
