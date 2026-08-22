from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from omakeyd import core


def compiled_rows(rows: tuple[tuple[str, ...], ...]) -> str:
    lines = ["xkb_keymap {", "xkb_symbols {" ]
    for codes, values in zip(core.ROW_CODES, rows):
        for code, value in zip(codes, values):
            upper = value.upper() if len(value) == 1 and value.isalpha() else core.SHIFTED_KEYSYM.get(value, value)
            lines.append(f"  key <{code}> {{ [ {value}, {upper} ] }};")
    lines.extend(["};", "};", ""])
    return "\n".join(lines)


COLEMAK_DH_YOGA_ROWS = (
    ("q", "w", "f", "p", "b", "j", "l", "u", "y", "semicolon"),
    ("a", "r", "s", "t", "g", "m", "n", "e", "i", "o"),
    ("z", "x", "c", "d", "v", "k", "h", "comma", "period", "slash"),
)


XKB_LIST = """layouts:
- layout: 'us'
  variant: ''
  brief: 'en'
  description: English (US)
- layout: 'us'
  variant: 'colemak_dh'
  brief: 'en'
  description: English (Colemak-DH)
- layout: 'fr'
  variant: ''
  brief: 'fr'
  description: French
"""


class FakeRunner:
    def __init__(self, keyboards: list[dict] | None = None) -> None:
        self.commands: list[list[str]] = []
        self.keyboards = keyboards or [
            {
                "name": "keyd-virtual-keyboard",
                "main": True,
                "layout": "us",
                "active_keymap": "English (US)",
            },
            {
                "name": "power-button",
                "main": False,
                "layout": "us",
                "active_keymap": "English (US)",
            },
        ]

    def __call__(self, command):
        command = list(command)
        self.commands.append(command)
        if command[:3] == ["xkbcli", "list", "--load-exotic"]:
            return core.CommandResult(0, XKB_LIST, "")
        if command[:2] == ["xkbcli", "compile-keymap"]:
            layout = command[command.index("--layout") + 1]
            variant = command[command.index("--variant") + 1] if "--variant" in command else ""
            if layout in ("colemak_dh_yoga",) or (layout == "us" and variant == "colemak_dh"):
                return core.CommandResult(0, compiled_rows(COLEMAK_DH_YOGA_ROWS), "")
            return core.CommandResult(0, compiled_rows(core.QWERTY_ROWS), "")
        if command[0] == "hyprctl" and "devices" in command:
            return core.CommandResult(0, json.dumps({"keyboards": self.keyboards}), "")
        if command[0] == "hyprctl" and "keyword" in command:
            return core.CommandResult(0, "ok\n", "")
        return core.CommandResult(1, "", f"Unexpected command: {command}")


class OmakeydCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.root / "config")})
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def write_keyd(self, content: str) -> Path:
        directory = self.root / "keyd"
        directory.mkdir(parents=True)
        path = directory / "laptop-colemak-dh.conf"
        path.write_text(content, encoding="utf-8")
        return path

    def test_parses_xkb_catalogue(self) -> None:
        entries = core.parse_xkbcli_list(XKB_LIST)
        self.assertEqual(entries[0]["layout"], "us")
        self.assertEqual(entries[0]["variant"], "")
        self.assertEqual(entries[1]["name"], "English (Colemak-DH)")
        self.assertEqual(entries[2]["brief"], "fr")

    def test_search_matches_name_layout_and_variant(self) -> None:
        entries = core.parse_xkbcli_list(XKB_LIST)
        self.assertEqual(core.search_catalog(entries, "colemak")[0]["variant"], "colemak_dh")
        self.assertEqual(core.search_catalog(entries, "fr")[0]["layout"], "fr")
        self.assertEqual(core.search_catalog(entries, "missing"), [])

    def test_parses_the_current_keyd_mapping_as_physical_rows(self) -> None:
        path = self.write_keyd(
            """[ids]
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
        )
        source = core.parse_keyd_config(path)
        self.assertIsNotNone(source)
        self.assertEqual(source["alias"], "Built-in keyboard")
        self.assertEqual(core.source_rows(source), [list(row) for row in COLEMAK_DH_YOGA_ROWS])
        self.assertEqual(source["mappings"]["AD03"], "AC04")  # physical E emits F
        self.assertEqual(source["mappings"]["AB07"], "AC06")  # physical M emits H

    def test_matches_keyd_source_to_custom_yoga_layout(self) -> None:
        path = self.write_keyd("[ids]\n*\n[main]\ne=f\nr=p\nt=b\ny=j\nu=l\ni=u\no=y\np=;\ns=r\nd=s\nf=t\nh=m\nj=n\nk=e\nl=i\n;=o\nv=d\nb=v\nn=k\nm=h\n")
        source = core.parse_keyd_config(path)
        runner = FakeRunner()
        matched = core.match_source_to_layout(
            source,
            [
                {
                    "layout": "colemak_dh_yoga",
                    "variant": "",
                    "name": "English (Colemak-DH Yoga)",
                    "brief": "DH",
                    "source": "custom",
                }
            ],
            runner,
        )
        self.assertEqual(matched["layout"], "colemak_dh_yoga")

    def test_compensation_inverts_source_positions_for_qwerty(self) -> None:
        source = {
            "name": "Colemak-DH Yoga",
            "mappings": {"AD03": "AC04", "AC04": "AD05"},
        }
        content = core.compensation_content(
            source,
            "us",
            "",
            "QWERTY (US)",
            compiled_rows(core.QWERTY_ROWS),
        )
        self.assertIn('include "us"', content)
        self.assertIn("key <AC04> { [ e, E ] };", content)
        self.assertIn("key <AD05> { [ f, F ] };", content)
        self.assertIn("corrected for Colemak-DH Yoga", content)

    def test_compensation_rejects_colliding_source_map(self) -> None:
        source = {"name": "Broken", "mappings": {"AD03": "AC04", "AD04": "AC04"}}
        with self.assertRaisesRegex(core.OmakeydError, "same position"):
            core.compensation_content(
                source, "us", "", "QWERTY", compiled_rows(core.QWERTY_ROWS)
            )

    def test_snapshot_filters_auxiliary_and_shadowed_devices(self) -> None:
        keyd_path = self.write_keyd("[ids]\n*\n[main]\ne=f\n")
        runner = FakeRunner(
            [
                {"name": "power-button", "main": False, "layout": "us", "active_keymap": "English (US)"},
                {"name": "at-translated-set-2-keyboard", "main": False, "layout": "colemak_dh_yoga", "active_keymap": "English (Colemak-DH Yoga)"},
                {"name": "keyd-virtual-keyboard", "main": True, "layout": "us", "active_keymap": "English (US)"},
                {"name": "logitech-pro-x", "main": False, "layout": "us", "active_keymap": "English (US)"},
            ]
        )
        config_file = self.root / "omakeyd.json"
        payload = core.snapshot("", 10, runner, config_file, keyd_path.parent)
        self.assertEqual([item["name"] for item in payload["keyboards"]], ["keyd-virtual-keyboard", "logitech-pro-x"])
        ignored = {item["name"]: item["reason"] for item in payload["ignoredKeyboards"]}
        self.assertEqual(ignored["power-button"], "auxiliary input")
        self.assertEqual(ignored["at-translated-set-2-keyboard"], "underlying device managed by keyd")

    def test_apply_generates_compensation_and_targets_only_selected_device(self) -> None:
        runner = FakeRunner()
        config_file = self.root / "omakeyd.json"
        config = core.empty_config()
        config["devices"]["keyd-virtual-keyboard"] = {
            "source": {
                "kind": "manual",
                "name": "Colemak-DH",
                "mappings": {"AD03": "AC04", "AC04": "AD05"},
            }
        }
        core.save_config(config, config_file)
        result = core.apply_layout(
            "keyd-virtual-keyboard",
            "us",
            "",
            "QWERTY (US)",
            "US",
            runner,
            config_file,
            self.root / "empty-keyd",
        )
        self.assertTrue(result["compensated"])
        self.assertTrue(result["runtimeLayout"].startswith("omakeyd_comp_"))
        generated = core.xkb_symbols_dir() / result["runtimeLayout"]
        self.assertTrue(generated.exists())
        keyword_commands = [command for command in runner.commands if "keyword" in command]
        self.assertGreaterEqual(len(keyword_commands), 2)
        self.assertTrue(all("keyd-virtual-keyboard" in " ".join(command) for command in keyword_commands))
        saved = core.load_config(config_file)
        self.assertEqual(saved["devices"]["keyd-virtual-keyboard"]["active"]["name"], "QWERTY (US)")

    def test_custom_layout_uses_the_exact_yoga_rows(self) -> None:
        runner = FakeRunner()
        config_file = self.root / "omakeyd.json"
        result = core.save_custom_layout(
            "Colemak-DH Yoga Copy",
            "DH",
            "us",
            "",
            "q w f p b j l u y semicolon",
            "a r s t g m n e i o",
            "z x c d v k h comma period slash",
            runner,
            config_file,
        )
        content = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("key <AD05> { [ b, B ] };", content)
        self.assertIn("key <AC06> { [ m, M ] };", content)
        self.assertIn("key <AB04> { [ d, D ] };", content)
        self.assertIn("key <AB07> { [ h, H ] };", content)
        self.assertIn(result["layout"]["layout"], core.load_config(config_file)["customLayouts"])

    def test_custom_row_count_fails_before_writing(self) -> None:
        runner = FakeRunner()
        with self.assertRaisesRegex(core.OmakeydError, "exactly 10"):
            core.save_custom_layout(
                "Short",
                "S",
                "us",
                "",
                "q w e",
                "a s d f g h j k l semicolon",
                "z x c v b n m comma period slash",
                runner,
                self.root / "config.json",
            )


if __name__ == "__main__":
    unittest.main()
