"""Suite, Komponente und installierter Build bleiben getrennte Angaben."""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    "suite": "1.3.3",
    "wavelink": "1.1.0",
    "hd60": "1.1.0",
    "driver": "0.1",
    "streamcontroller": "1.1.0",
    "spotify": "1.2.0",
    "bar": "1.0.0",
}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class VersionPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.versions = load_module(
            "elgato_versions_under_test", ROOT / "packaging" / "common" / "versions.py"
        )

    def test_declared_versions_stay_independent(self):
        suite = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(suite, EXPECTED["suite"])
        found = {
            "wavelink": (ROOT / "wave-link-linux" / "VERSION").read_text(encoding="utf-8").strip(),
            "hd60": (ROOT / "capture-card" / "VERSION").read_text(encoding="utf-8").strip(),
            "driver": (ROOT / "capture-card" / "DRIVER_VERSION").read_text(encoding="utf-8").strip(),
            "streamcontroller": (
                ROOT
                / "wave-link-linux/streamcontroller_plugin/com_wavelink_linux/VERSION"
            )
            .read_text(encoding="utf-8")
            .strip(),
            "spotify": (ROOT / "wave-link-linux/Spotify/VERSION").read_text(encoding="utf-8").strip(),
            "bar": (
                ROOT
                / "wave-link-linux/streamcontroller_plugin/sd_plus_bar_wallpapers"
                / "com_wavelink_linux_bar/VERSION"
            )
            .read_text(encoding="utf-8")
            .strip(),
        }
        for name, value in found.items():
            self.assertEqual(value, EXPECTED[name], name)
            self.assertNotEqual(value, suite, name)
        self.assertNotEqual(found["driver"], found["hd60"])
        self.assertNotEqual(found["wavelink"], "1.0.0")
        self.assertNotEqual(found["streamcontroller"], "1.0.0")

    def test_plugin_manifests_follow_their_own_version_files(self):
        pairs = {
            "streamcontroller": ROOT
            / "wave-link-linux/streamcontroller_plugin/com_wavelink_linux/manifest.json",
            "spotify": ROOT / "wave-link-linux/Spotify/manifest.json",
            "bar": ROOT
            / "wave-link-linux/streamcontroller_plugin/sd_plus_bar_wallpapers"
            / "com_wavelink_linux_bar/manifest.json",
        }
        for name, path in pairs.items():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["version"], EXPECTED[name])
        for name in ("streamcontroller", "spotify"):
            data = json.loads(pairs[name].read_text(encoding="utf-8"))
            self.assertEqual(data["minimum-app-version"], "1.0.0")
            self.assertEqual(data["app-version"], "1.5.0-beta")

    def test_checker_accepts_this_tree_and_rejects_a_foreign_suite(self):
        self.assertEqual(self.versions.check(ROOT), [])
        problems = self.versions.check(ROOT, suite="9.9.9")
        self.assertTrue(problems)
        self.assertEqual(self.versions.check(ROOT, suite="0.0.0-ci.20261106010101"), [])

    def test_running_checkout_reports_component_suite_and_revision(self):
        wavelink = load_module(
            "wavelink_version_under_test",
            ROOT / "wave-link-linux/wavelink_linux/version.py",
        )
        info = wavelink.identity()
        self.assertEqual(info["component_version"], EXPECTED["wavelink"])
        self.assertEqual(info["suite_version"], EXPECTED["suite"])
        self.assertEqual(info["installed_build"], EXPECTED["suite"])
        self.assertNotEqual(info["component_version"], info["suite_version"])
        revision = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "--short=12", "HEAD"],
            text=True,
        ).strip()
        self.assertEqual(info["revision"], revision)
        about = wavelink.about_fields()
        self.assertEqual(about["version"], EXPECTED["wavelink"])
        self.assertIn(f"Komponente {EXPECTED['wavelink']}", about["comments"])
        self.assertIn(f"Elgato for Linux {EXPECTED['suite']}", about["comments"])
        self.assertNotIn("Treiber hd60s", about["comments"])

        sys.path.insert(0, str(ROOT / "wave-link-linux"))
        import wavelink_linux

        self.assertEqual(wavelink_linux.__version__, EXPECTED["wavelink"])
        self.assertNotEqual(wavelink_linux.__version__, "1.0.0")

        hd60 = load_module(
            "hd60_version_under_test", ROOT / "capture-card/version_info.py"
        )
        hd_about = hd60.about_fields()
        self.assertEqual(hd_about["version"], EXPECTED["hd60"])
        self.assertEqual(hd_about["driver_version"], EXPECTED["driver"])
        self.assertEqual(hd_about["suite_version"], EXPECTED["suite"])
        self.assertIn("Treiber hd60s/0.1 (unabhängig)", hd_about["comments"])
        self.assertNotIn(f"Treiber hd60s/{EXPECTED['suite']}", hd_about["comments"])
        self.assertNotIn(f"Treiber hd60s/{EXPECTED['hd60']}", hd_about["comments"])

    def test_stamp_does_not_rewrite_component_versions(self):
        with tempfile.TemporaryDirectory(prefix="elgato-ver-") as raw:
            root = Path(raw)
            (root / "VERSION").write_text("1.3.3\n", encoding="utf-8")
            (root / "wave-link-linux").mkdir()
            (root / "capture-card").mkdir()
            (root / "wave-link-linux/VERSION").write_text("1.1.0\n", encoding="utf-8")
            (root / "capture-card/VERSION").write_text("1.1.0\n", encoding="utf-8")
            (root / "capture-card/DRIVER_VERSION").write_text("0.1\n", encoding="utf-8")
            before = {
                path: path.read_text(encoding="utf-8")
                for path in root.rglob("VERSION")
            }
            before[root / "capture-card/DRIVER_VERSION"] = (
                root / "capture-card/DRIVER_VERSION"
            ).read_text(encoding="utf-8")
            dest = root / "out"
            self.versions.stamp(root, dest, "hd60", suite="0.0.0-ci.20261106010101")
            payload = json.loads((dest / "build-info.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["component_version"], "1.1.0")
            self.assertEqual(payload["driver_version"], "0.1")
            self.assertEqual(payload["suite_version"], "0.0.0-ci.20261106010101")
            for path, text in before.items():
                self.assertEqual(path.read_text(encoding="utf-8"), text)
            with self.assertRaises(ValueError):
                self.versions.stamp(root, dest, "wavelink", suite="9.9.9")

    def test_installed_copy_ignores_stale_component_in_build_info(self):
        with tempfile.TemporaryDirectory(prefix="elgato-inst-") as raw:
            dest = Path(raw)
            (dest / "VERSION").write_text("1.1.0\n", encoding="utf-8")
            (dest / "DRIVER_VERSION").write_text("0.1\n", encoding="utf-8")
            (dest / "build-info.json").write_text(
                json.dumps(
                    {
                        "component_version": "1.0.0",
                        "driver_version": "1.3.3",
                        "revision": "abc123def456",
                        "suite_version": "1.3.3",
                    }
                ),
                encoding="utf-8",
            )
            shutil.copy(ROOT / "packaging/common/versions.py", dest / "_elgato_versions.py")
            shutil.copy(ROOT / "capture-card/version_info.py", dest / "version_info.py")
            module = load_module("hd60_installed_under_test", dest / "version_info.py")
            about = module.about_fields()
            self.assertEqual(about["version"], "1.1.0")
            self.assertEqual(about["component_version"], "1.1.0")
            self.assertEqual(about["driver_version"], "0.1")
            self.assertEqual(about["suite_version"], "1.3.3")
            self.assertEqual(about["installed_build"], "1.3.3")
            self.assertEqual(about["revision"], "abc123def456")
            self.assertIn("Treiber hd60s/0.1 (unabhängig)", about["comments"])

    def test_installed_copy_inside_unrelated_git_keeps_its_stamp(self):
        with tempfile.TemporaryDirectory(prefix="elgato-foreign-git-") as raw:
            outer = Path(raw)
            subprocess.run(["git", "init"], cwd=outer, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=outer,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "test"], cwd=outer, check=True)
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "unrelated"],
                cwd=outer,
                check=True,
                capture_output=True,
            )
            dest = outer / "share" / "wavelink-linux"
            pkg = dest / "wavelink_linux"
            pkg.mkdir(parents=True)
            (dest / "VERSION").write_text("1.1.0\n", encoding="utf-8")
            (dest / "build-info.json").write_text(
                json.dumps(
                    {
                        "component_version": "1.0.0",
                        "revision": "abc123def456",
                        "suite_version": "1.3.3",
                    }
                ),
                encoding="utf-8",
            )
            shutil.copy(ROOT / "packaging/common/versions.py", pkg / "_elgato_versions.py")
            shutil.copy(ROOT / "wave-link-linux/wavelink_linux/version.py", pkg / "version.py")
            module = load_module("wavelink_foreign_git_under_test", pkg / "version.py")
            info = module.identity()
            foreign = subprocess.check_output(
                ["git", "-C", str(outer), "rev-parse", "--short=12", "HEAD"],
                text=True,
            ).strip()
            self.assertEqual(info["component_version"], "1.1.0")
            self.assertEqual(info["suite_version"], "1.3.3")
            self.assertEqual(info["revision"], "abc123def456")
            self.assertNotEqual(info["revision"], foreign)

    def test_git_checkout_ignores_a_stale_build_stamp(self):
        with tempfile.TemporaryDirectory(prefix="elgato-git-") as raw:
            root = Path(raw)
            (root / "VERSION").write_text("1.3.3\n", encoding="utf-8")
            (root / "capture-card").mkdir()
            app = root / "wave-link-linux"
            pkg = app / "wavelink_linux"
            pkg.mkdir(parents=True)
            (app / "VERSION").write_text("1.1.0\n", encoding="utf-8")
            (app / "build-info.json").write_text(
                json.dumps(
                    {
                        "component_version": "1.0.0",
                        "revision": "deadbeefdead",
                        "suite_version": "1.0.0",
                    }
                ),
                encoding="utf-8",
            )
            shutil.copy(ROOT / "packaging/common/versions.py", pkg / "_elgato_versions.py")
            shutil.copy(ROOT / "wave-link-linux/wavelink_linux/version.py", pkg / "version.py")
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=root,
                check=True,
            )
            subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "init"],
                cwd=root,
                check=True,
                capture_output=True,
            )
            module = load_module("wavelink_git_under_test", pkg / "version.py")
            info = module.identity()
            live = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
                text=True,
            ).strip()
            self.assertEqual(info["component_version"], "1.1.0")
            self.assertEqual(info["suite_version"], "1.3.3")
            self.assertEqual(info["installed_build"], "1.3.3")
            self.assertEqual(info["revision"], live)
            self.assertNotEqual(info["revision"], "deadbeefdead")

    def test_userspace_refresh_does_not_touch_audio_or_driver_services(self):
        install_sh = (ROOT / "capture-card/install.sh").read_text(encoding="utf-8")
        body = re.search(
            r"\ninstall_program_files\(\) \{(?P<body>.*?)\n\}", install_sh, re.S
        )
        self.assertIsNotNone(body)
        for word in ("dkms", "modprobe", "dnf", "systemctl", "mokutil"):
            self.assertNotIn(word, body.group("body"))
        remainder = install_sh.split('if [[ "${USERSPACE}" -eq 1 ]]; then', 1)[1]
        self.assertLess(remainder.find("exit 0"), remainder.find("dnf install"))

        install_core = load_module(
            "install_core_under_test", ROOT / "wave-link-linux/install_core.py"
        )
        source = inspect.getsource(install_core.install_userspace)
        for word in ("_install_pipewire", "ensure_pipewire", "systemctl", "pip"):
            self.assertNotIn(word, source)
        self.assertIn("_install_pipewire", inspect.getsource(install_core.install_app))

    def test_plugins_read_version_files(self):
        dial = load_module(
            "dial_version_under_test",
            ROOT
            / "wave-link-linux/streamcontroller_plugin/com_wavelink_linux/version_info.py",
        )
        spotify = load_module(
            "spotify_version_under_test",
            ROOT / "wave-link-linux/Spotify/version_info.py",
        )
        self.assertEqual(dial.read_plugin_version(), EXPECTED["streamcontroller"])
        self.assertEqual(spotify.read_plugin_version(), EXPECTED["spotify"])

    def test_installer_label_uses_suite_file(self):
        chooser = load_module(
            "chooser_under_test", ROOT / "packaging/common/chooser.py"
        )
        self.assertEqual(chooser.release_label(), EXPECTED["suite"])


if __name__ == "__main__":
    unittest.main()
