"""tools/build_exe.py без самой сборки: что кладётся в сборку и иконка."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from organism_atlas import atlas_cache

ROOT = Path(__file__).resolve().parent.parent


def load_tool(name="build_exe"):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BuildExeTests(unittest.TestCase):
    def test_sources_for_cache_version_are_bundled(self):
        """в сборке - все исходники, по которым atlas_cache.version() считает версию, на тех же местах"""
        tool = load_tool()
        bundled = {(dest / src.name).as_posix() for src, dest in tool.source_datas()}
        pkg = atlas_cache.PKG
        expected = set()
        for name in atlas_cache._SOURCES:
            p = pkg / name
            for f in (p.rglob("*.py") if p.is_dir() else [p]):
                expected.add("organism_atlas/" + f.relative_to(pkg).as_posix())
        self.assertEqual(bundled, expected)
        self.assertIn("organism_atlas/body/muscles.py", bundled)

    def test_icon(self):
        tool = load_tool()
        with tempfile.TemporaryDirectory() as tmp:
            path = tool.make_icon(Path(tmp) / "a.ico")
            with Image.open(path) as im:
                self.assertEqual(im.format, "ICO")
                self.assertIn((256, 256), im.info["sizes"])
                self.assertIn((16, 16), im.info["sizes"])

    def test_version_survives_missing_sources(self):
        """если исходников рядом нет, версия всё равно считается (кэш просто не следит за правками)"""
        old = atlas_cache.PKG
        try:
            atlas_cache.PKG = Path(tempfile.mkdtemp())
            self.assertEqual(len(atlas_cache.version()), 16)
        finally:
            atlas_cache.PKG = old


class BuildSetupTests(unittest.TestCase):
    """tools/build_setup.py и tools/setup.iss без Inno Setup"""

    def test_script_matches_build(self):
        raw = (ROOT / "tools" / "setup.iss").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "без BOM Inno Setup испортит русский текст")
        text = raw.decode("utf-8-sig")
        name = load_tool().NAME
        self.assertIn('#define AppExe "%s.exe"' % name, text)
        self.assertIn("OutputBaseFilename=%s-Setup-{#AppVersion}" % name, text)
        self.assertIn(r"{localappdata}\organism_atlas\cache", text)       # там atlas_cache хранит кэш
        self.assertIn(r"{userappdata}\organism_atlas", text)               # а settings.py - настройки

    def test_iscc_command(self):
        from organism_atlas import __version__
        cmd = load_tool("build_setup").iscc_command("ISCC.exe")
        self.assertEqual(cmd[0], "ISCC.exe")
        self.assertIn("/DAppVersion=" + __version__, cmd)
        self.assertTrue(cmd[-1].endswith("setup.iss"))
        for opt in ("/DDist=", "/DIcon=", "/DOutDir="):
            self.assertEqual(sum(c.startswith(opt) for c in cmd), 1, opt)


if __name__ == "__main__":
    unittest.main()
