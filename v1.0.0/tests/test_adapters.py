import json
import os
import stat
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tes import adapters
from tes.adapters.alacritty import Alacritty
from tes.adapters.gnome_terminal import GnomeTerminal
from tes.adapters.kitty import Kitty
from tes.adapters.konsole import Konsole
from tes.core import backups, paths, themes

FAKE_GSETTINGS = r'''#!/usr/bin/env python3
import json, os, sys
store_path = os.environ["FAKE_GS_STORE"]
store = json.load(open(store_path)) if os.path.exists(store_path) else {}
a = sys.argv[1:]
cmd, schema = a[0], a[1]
def save(): json.dump(store, open(store_path, "w"))
if cmd == "get":
    key = a[2]
    if schema == "org.gnome.Terminal.ProfilesList" and key == "default":
        print("'abc-123'"); sys.exit(0)
    print(store.get(schema + "|" + key, "'<default>'")); sys.exit(0)
if cmd == "set":
    store[schema + "|" + a[2]] = a[3]; save(); sys.exit(0)
if cmd == "reset":
    store.pop(schema + "|" + a[2], None); save(); sys.exit(0)
sys.exit(1)
'''


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = dict(os.environ)
        for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
            os.environ.pop(k, None)
        os.environ["HOME"] = self.tmp.name
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._old)))
        self.theme = themes.PRESETS["Dracula"].with_(font="JetBrains Mono", font_size=13, opacity=85, cursor_shape="beam")


class KittyTests(Sandbox):
    def test_apply_preserves_user_config_and_reset_restores_it(self):
        conf = Kitty.conf(); conf.parent.mkdir(parents=True)
        original = "font_size 9\nmap ctrl+t new_tab\n"
        conf.write_text(original)
        res = Kitty().apply(self.theme)
        self.assertTrue(res.ok); self.assertTrue(conf.read_text().startswith(original.rstrip()))
        self.assertIn("include tes-theme.conf", conf.read_text())
        t = Kitty.theme_file().read_text()
        for needle in ("foreground #f8f8f2", "background #282a36", "color15 #ffffff", "font_family JetBrains Mono",
                       "font_size 13", "cursor_shape beam", "background_opacity 0.85"):
            self.assertIn(needle, t)
        Kitty().apply(self.theme)  # idempotent
        self.assertEqual(conf.read_text().count("include tes-theme.conf"), 1)
        Kitty().reset()
        self.assertEqual(conf.read_text().strip(), original.strip())
        self.assertFalse(Kitty.theme_file().exists())

    def test_background_image_rules(self):
        png = Path(self.tmp.name) / "bg.png"; png.write_bytes(b"x")
        self.assertIn("background_image " + str(png), Kitty().render(self.theme.with_(bg_image=str(png))))
        res = Kitty().apply(self.theme.with_(bg_image=str(Path(self.tmp.name) / "bg.jpg")))
        self.assertIn("bg_image", res.skipped)

    def test_creates_config_when_missing_and_undo_removes_it(self):
        self.assertFalse(Kitty.conf().exists())
        res = Kitty().apply(self.theme)
        self.assertTrue(Kitty.conf().exists())
        backups.restore(backups.entry_for(res.backup))
        self.assertFalse(Kitty.conf().exists())


class AlacrittyTests(Sandbox):
    def parse(self):
        return tomllib.loads(Alacritty.conf().read_text())

    def test_theme_file_is_valid_toml_with_expected_values(self):
        d = tomllib.loads(Alacritty().render(self.theme))
        self.assertEqual(d["colors"]["primary"]["background"], "#282a36")
        self.assertEqual(d["colors"]["bright"]["white"], "#ffffff")
        self.assertEqual(d["font"]["normal"]["family"], "JetBrains Mono")
        self.assertEqual(d["window"]["opacity"], 0.85)
        self.assertEqual(d["cursor"]["style"]["shape"], "Beam")

    def test_new_config(self):
        self.assertTrue(Alacritty().apply(self.theme).ok)
        self.assertIn("import", self.parse()["general"])

    def test_existing_config_without_general(self):
        Alacritty.conf().parent.mkdir(parents=True)
        Alacritty.conf().write_text('[window]\nopacity = 1\n\n[font]\nsize = 9\n')
        Alacritty().apply(self.theme)
        d = self.parse()
        self.assertEqual(d["font"]["size"], 9); self.assertIn("import", d["general"])

    def test_existing_general_table_is_not_duplicated(self):
        Alacritty.conf().parent.mkdir(parents=True)
        Alacritty.conf().write_text('[general]\nlive_config_reload = true\n\n[window]\nopacity = 1\n')
        res = Alacritty().apply(self.theme)
        d = self.parse()   # would raise if [general] were duplicated
        self.assertTrue(res.ok); self.assertTrue(d["general"]["live_config_reload"]); self.assertIn("import", d["general"])
        Alacritty().apply(self.theme)   # re-apply keeps a single, valid block
        self.assertEqual(Alacritty.conf().read_text().count("import ="), 1); self.parse()

    def test_existing_import_is_never_overwritten(self):
        Alacritty.conf().parent.mkdir(parents=True)
        orig = '[general]\nimport = ["/my/theme.toml"]\n'
        Alacritty.conf().write_text(orig)
        res = Alacritty().apply(self.theme)
        self.assertEqual(Alacritty.conf().read_text(), orig)
        self.assertTrue(any("import list" in n for n in res.notes))

    def test_reset(self):
        Alacritty().apply(self.theme); Alacritty().reset()
        self.assertNotIn("import", Alacritty.conf().read_text())
        self.assertFalse(Alacritty.theme_file().exists())


class KonsoleTests(Sandbox):
    def test_files(self):
        res = Konsole().apply(self.theme)
        d = Konsole.dir()
        scheme = (d / "TerminalExperienceStudio.colorscheme").read_text()
        self.assertIn("[Background]\nColor=40,42,54", scheme); self.assertIn("Opacity=0.85", scheme)
        prof = (d / "Terminal Experience Studio.profile").read_text()
        self.assertIn("CursorShape=1", prof); self.assertIn("JetBrains Mono,13", prof)
        self.assertTrue(res.notes)
        Konsole().reset(); self.assertFalse(list(d.iterdir()))


class GnomeTests(Sandbox):
    def setUp(self):
        super().setUp()
        bindir = Path(self.tmp.name) / "bin"; bindir.mkdir()
        gs = bindir / "gsettings"; gs.write_text(FAKE_GSETTINGS); gs.chmod(gs.stat().st_mode | stat.S_IEXEC)
        (bindir / "gnome-terminal").write_text("#!/bin/sh\n"); (bindir / "gnome-terminal").chmod(0o755)
        os.environ["PATH"] = f"{bindir}:{os.environ['PATH']}"
        os.environ["FAKE_GS_STORE"] = str(Path(self.tmp.name) / "store.json")

    def store(self):
        p = Path(os.environ["FAKE_GS_STORE"])
        return json.loads(p.read_text()) if p.exists() else {}

    def key(self, k):
        return self.store().get("org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:abc-123/|" + k)

    def test_detect_apply_undo(self):
        gt = GnomeTerminal(); self.assertTrue(gt.detect())
        res = gt.apply(self.theme)
        self.assertTrue(res.ok, res.message)
        self.assertEqual(self.key("background-color"), "'#282a36'")
        self.assertEqual(self.key("font"), "'JetBrains Mono 13'")
        self.assertEqual(self.key("cursor-shape"), "'ibeam'")
        self.assertEqual(self.key("background-transparency-percent"), "15")
        self.assertEqual(self.key("use-transparent-background"), "true")
        self.assertTrue(self.key("palette").startswith("['#21222c', '#ff5555'"))
        self.assertIn("bg_image", gt.apply(self.theme.with_(bg_image="/x.png")).skipped)
        # undo restores the pre-apply values (which were the fake defaults)
        first_backup = res.backup
        backups.restore(backups.entry_for(first_backup))
        self.assertEqual(self.key("background-color"), "'<default>'")

    def test_reset_clears_keys_and_is_itself_undoable(self):
        gt = GnomeTerminal(); gt.apply(self.theme)
        res = gt.reset()
        self.assertIsNone(self.key("background-color"))
        backups.restore(backups.entry_for(res.backup))
        self.assertEqual(self.key("background-color"), "'#282a36'")


class RegistryTests(Sandbox):
    def test_detect_nothing_installed(self):
        os.environ["PATH"] = "/nonexistent"
        self.assertEqual(adapters.detect_all(), [])

    def test_every_adapter_declares_known_features(self):
        for a in adapters.ALL:
            self.assertTrue(a.features <= set(adapters.FEATURES), a.id)
        self.assertNotIn("bg_image", adapters.BY_ID["gnome-terminal"].features)
        self.assertIn("bg_image", adapters.BY_ID["kitty"].features)

    def test_backup_listing_includes_legacy_mvp_backups(self):
        (Path(self.tmp.name) / ".bashrc.terminal-experience-backup-20250102-030405").write_text("old")
        found = backups.list_backups()
        self.assertEqual(len(found), 1); self.assertTrue(found[0].legacy)
        self.assertEqual(found[0].created.year, 2025)


if __name__ == "__main__":
    unittest.main()
