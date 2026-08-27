from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class PluginContractTests(unittest.TestCase):
    def test_manifest_declares_service_and_bar_widget(self) -> None:
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "io.github.olivoil.omakeyd")
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(set(manifest["kinds"]), {"service", "bar-widget"})
        self.assertEqual(manifest["barWidget"]["defaultSection"], "right")
        for entrypoint in manifest["entryPoints"].values():
            self.assertTrue((ROOT / entrypoint).is_file())

    def test_qml_uses_the_keyd_profile_backend(self) -> None:
        widget = (ROOT / "Omakeyd.qml").read_text(encoding="utf-8")
        panel = (ROOT / "Panel.qml").read_text(encoding="utf-8")
        self.assertIn('Qt.resolvedUrl("bin/omakeyd")', widget)
        self.assertIn('"--profile", selectedProfileId', panel)
        self.assertIn('"--layout-id", String(layout.id || "")', panel)
        self.assertIn('"\\uf11c"', widget)
        self.assertNotIn("FIND A LAYOUT", panel)
        self.assertNotIn("PHYSICAL REMAP", panel)

    def test_backend_is_executable(self) -> None:
        backend = ROOT / "bin" / "omakeyd"
        self.assertTrue(backend.stat().st_mode & 0o111)

    def test_privileged_helpers_are_explicit_and_executable(self) -> None:
        for name in ("omakeyd-helper", "omakeyd-setup"):
            helper = ROOT / "helper" / name
            self.assertTrue(helper.is_file())
            self.assertTrue(helper.stat().st_mode & 0o111)
        policy = (ROOT / "helper" / "io.github.olivoil.omakeyd.policy").read_text(
            encoding="utf-8"
        )
        self.assertIn("/usr/local/libexec/omakeyd-helper", policy)
        self.assertIn("<allow_active>yes</allow_active>", policy)


if __name__ == "__main__":
    unittest.main()
