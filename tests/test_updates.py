"""Проверка обновлений и сборка для разных систем - без сети и без PyInstaller."""

import datetime
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from organism_atlas import settings, updates

ROOT = Path(__file__).resolve().parent.parent
DAY = datetime.date(2026, 11, 2)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(payload):
    def open_(req, timeout):
        open_.req = req
        return FakeResponse(json.dumps(payload).encode("utf-8"))
    return open_


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"ORGANISM_ATLAS_SETTINGS": os.path.join(self.tmp.name, "s.json"),
                                           "ORGANISM_ATLAS_NO_UPDATE_CHECK": ""})
        env.start()
        self.addCleanup(env.stop)

    def test_versions(self):
        self.assertEqual(updates.parse("v1.2.10"), (1, 2, 10))
        self.assertIsNone(updates.parse("latest"))
        self.assertTrue(updates.newer("v1.10.0", "1.9.3"))
        self.assertTrue(updates.newer("v2", "1.9.9"))
        self.assertFalse(updates.newer("v1.0", "1.0.0"))
        self.assertFalse(updates.newer("nightly", "1.0.0"))

    def test_check_newer_release(self):
        url = "https://github.com/%s/releases/tag/v99.0.0" % updates.REPO
        info = updates.check(opener({"tag_name": "v99.0.0", "html_url": url}), today=DAY)
        self.assertEqual(info, {"version": "99.0.0", "url": url})
        self.assertEqual(settings.load()["update_checked"], DAY.isoformat())
        self.assertFalse(updates.due(today=DAY))                       # сегодня уже проверяли
        self.assertTrue(updates.due(today=DAY + datetime.timedelta(days=1)))

    def test_release_url_must_be_github(self):
        """адрес из ответа открывается в браузере: не GitHub (или не https) - страница выпусков по умолчанию"""
        default = "https://github.com/%s/releases" % updates.REPO
        for url in ("file:///C:/Windows/System32/calc.exe", "http://github.com/x", "ms-settings:", 5, None):
            info = updates.check(opener({"tag_name": "v99.0.0", "html_url": url}), today=DAY)
            self.assertEqual(info["url"], default, url)

    def test_same_version_and_errors_are_silent(self):
        self.assertIsNone(updates.check(opener({"tag_name": "v0.1.0"}), today=DAY))

        def broken(req, timeout):
            raise OSError("нет сети")
        self.assertIsNone(updates.check(broken, today=DAY))

    def test_can_be_turned_off(self):
        settings.save(updates="off")
        self.assertFalse(updates.due(today=DAY))
        settings.save(updates="on")
        self.assertTrue(updates.due(today=DAY))
        with mock.patch.dict(os.environ, {"ORGANISM_ATLAS_NO_UPDATE_CHECK": "1"}):
            self.assertFalse(updates.due(today=DAY))


class CrossPlatformBuildTests(unittest.TestCase):
    def tool(self):
        spec = importlib.util.spec_from_file_location("build_exe", ROOT / "tools" / "build_exe.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_icons_and_names(self):
        tool = self.tool()
        self.assertEqual([tool.platform_tag(p) for p in ("win32", "darwin", "linux")], ["windows", "macos", "linux"])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(tool.icon_for(Path(tmp), "win32").suffix, ".ico")
            self.assertEqual(tool.icon_for(Path(tmp), "darwin").suffix, ".png")
            self.assertIsNone(tool.icon_for(Path(tmp), "linux"))

    def test_linux_archive_keeps_folder(self):
        import tarfile
        tool = self.tool()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp, "OrganismAtlas")
            out.mkdir()
            (out / "OrganismAtlas").write_text("#!/bin/sh\n")
            with mock.patch.object(tool, "ROOT", Path(tmp)):
                Path(tmp, "dist").mkdir()
                path = tool.archive(out, "linux")
            self.assertTrue(path.name.endswith("-linux.tar.gz"))
            with tarfile.open(path) as tar:
                self.assertIn("OrganismAtlas/OrganismAtlas", tar.getnames())

    def test_macos_archive_name_keeps_version(self):
        """имя архива - с полной версией и системой (точка в версии - не расширение)"""
        tool = self.tool()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(tool, "ROOT", Path(tmp)), \
                mock.patch.object(tool, "__version__", "1.1.0"), mock.patch("subprocess.run") as run:
            path = tool.archive(Path(tmp, "dist", "OrganismAtlas.app"), "darwin")
        self.assertEqual(path.name, "OrganismAtlas-1.1.0-macos.zip")
        self.assertEqual(run.call_args[0][0][:4], ["ditto", "-c", "-k", "--keepParent"])

    def test_workflow_builds_every_system_and_releases_once(self):
        text = (ROOT / ".github" / "workflows" / "setup.yml").read_text(encoding="utf-8")
        for needle in ("windows-latest", "ubuntu-latest", "macos-latest", "build_exe.py --archive",
                       "needs: [draft, setup, portable]", "gh release create", "--draft --target"):
            self.assertIn(needle, text)
        self.assertEqual(text.count("gh release upload"), 2)
        self.assertEqual(text.count('--draft=false --latest'), 1)


if __name__ == "__main__":
    unittest.main()
