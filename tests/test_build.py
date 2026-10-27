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
    def test_stamp_gives_same_cache_version(self):
        """в сборке исходников рисунка нет, вместо них - их хэш (STAMP): версия кэша та же, что из исходников"""
        import shutil
        tool = load_tool()
        v = atlas_cache.version()
        old = atlas_cache.PKG
        with tempfile.TemporaryDirectory() as tmp:
            tool.write_stamp(Path(tmp) / atlas_cache.STAMP)     # сборка считает хэш по исходникам
            try:
                atlas_cache.PKG = Path(tmp)                      # «собранная программа»: только данные
                self.assertNotEqual(atlas_cache.sources_digest(), (Path(tmp) / atlas_cache.STAMP).read_text().strip())
                self.assertEqual(atlas_cache.version(), v)
            finally:
                atlas_cache.PKG = old
                shutil.rmtree(tmp, ignore_errors=True)

    def test_commands_bundle_data_and_stamp(self):
        """обе сборки кладут данные пакета, хэш исходников и бэкенды OpenGL, но не tkinter"""
        tool = load_tool()
        icon, stamp = Path("a.ico"), Path("stamp.txt")
        nk = tool.nuitka_command(icon, stamp)
        self.assertIn("--mode=standalone", nk)
        self.assertIn("--include-package-data=organism_atlas", nk)
        self.assertIn("--include-package=glcontext", nk)
        self.assertIn("--include-data-files=stamp.txt=organism_atlas/" + atlas_cache.STAMP, nk)
        self.assertIn("--nofollow-import-to=tkinter", nk)
        self.assertIn("--windows-console-mode=disable", nk)
        self.assertIn("--mode=onefile", tool.nuitka_command(icon, stamp, onefile=True))
        pi = tool.pyinstaller_command(icon, stamp, console=True)
        self.assertIn("--console", pi)
        self.assertEqual(pi[pi.index("--collect-data") + 1], "organism_atlas")
        self.assertTrue(any(a.startswith("stamp.txt") and a.endswith("organism_atlas") for a in pi))
        self.assertEqual(pi[pi.index("--exclude-module") + 1], "tkinter")

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


class SelftestTests(unittest.TestCase):
    def test_selftest_from_sources(self):
        """run.py --selftest: окно, 3D-кадр, отчёт и код 0 - так build_exe.py проверяет собранную программу"""
        import sys
        tool = load_tool()
        tool_exe = [sys.executable, str(ROOT / "run.py")]
        with tempfile.TemporaryDirectory() as tmp:
            import os
            import subprocess
            report = Path(tmp) / "r.txt"
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", ORGANISM_ATLAS_SETTINGS=str(Path(tmp) / "s.json"),
                       ORGANISM_ATLAS_PROGRESS=str(Path(tmp) / "p.json"), ORGANISM_ATLAS_CACHE=tmp)
            r = subprocess.run(tool_exe + ["--selftest=" + str(report)], env=env, timeout=300)
            self.assertEqual(r.returncode, 0, report.read_text(encoding="utf-8") if report.exists() else "")
            text = report.read_text(encoding="utf-8")
            self.assertIn("window", text)
            self.assertIn("3d", text)
            self.assertFalse(os.path.exists(env["ORGANISM_ATLAS_SETTINGS"]))       # настройки не тронуты
        self.assertTrue(callable(tool.selftest))


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

    def test_wizard_is_short(self):
        """мастер: только выбор папки и «Готово» - без вопросов про язык, права, группу и ярлыки"""
        text = (ROOT / "tools" / "setup.iss").read_text(encoding="utf-8-sig")
        for line in ("DisableDirPage=no", "DisableWelcomePage=yes", "DisableReadyPage=yes",
                     "DisableProgramGroupPage=yes", "ShowLanguageDialog=no",
                     "PrivilegesRequiredOverridesAllowed=commandline"):
            self.assertIn(line, text.splitlines())
        self.assertNotIn("[Tasks]", text)

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
