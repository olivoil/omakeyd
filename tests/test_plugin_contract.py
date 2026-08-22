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
        for entrypoint in manifest["entryPoints"].values():
            self.assertTrue((ROOT / entrypoint).is_file())

    def test_qml_uses_the_self_contained_backend(self) -> None:
        widget = (ROOT / "Omakeyd.qml").read_text(encoding="utf-8")
        panel = (ROOT / "Panel.qml").read_text(encoding="utf-8")
        self.assertIn('Qt.resolvedUrl("bin/omakeyd")', widget)
        self.assertIn('"--device", selectedDevice', panel)
        self.assertNotIn("/etc/keyd", widget + panel)

    def test_backend_is_executable(self) -> None:
        backend = ROOT / "bin" / "omakeyd"
        self.assertTrue(backend.stat().st_mode & 0o111)


if __name__ == "__main__":
    unittest.main()
