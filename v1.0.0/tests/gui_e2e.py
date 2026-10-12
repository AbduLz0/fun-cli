"""End-to-end GUI test: drives the real window in a sandboxed HOME. Run under xvfb:
   GSK_RENDERER=cairo xvfb-run -a python3 tests/gui_e2e.py"""
import os, subprocess, sys, tempfile, traceback
home = tempfile.mkdtemp(); os.environ["HOME"] = home
for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"): os.environ.pop(k, None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, GLib, GdkPixbuf
from pathlib import Path
from tes.ui.app import StudioApp
from tes.core import paths, bashconfig, backups

Path(home, ".bashrc").write_text("alias keepme='echo hi'\n")
results = []
def check(name, cond, extra=""):
    results.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name, extra)

Adw.init(); app = StudioApp()
steps = []
def run():
    win = app.props.active_window
    if win is None: return True
    try:
        st = win.state
        for pid in win.nav_ids:                       # every page opens without error
            win.navigate(pid)
        check("all 7 pages build and open", len(win.pages) == 7)

        w = win.pages["welcome"]
        w.greeting.set_text("Hello {user}")
        w._face_toggled(w._faces["(⌐■_■)"], "(⌐■_■)") if False else w._faces["(⌐■_■)"].set_active(True)
        check("welcome: face + greeting saved to state", st.s["face"] == "(⌐■_■)" and st.s["greeting"] == "Hello {user}")
        check("welcome: status becomes 'none' before apply", st.sync_status() == "none")

        p = win.pages["prompt"]
        p.checks["two_line"].set_active(True)
        check("prompt: preset saved", st.s["prompt_preset"] == "two_line")
        p.dots["#6ea8fe"].set_active(True)
        check("prompt: accent changes live", st.s["accent"] == "#6ea8fe")

        a = win.pages["ascii"]
        a._use_text(__import__("tes.core.content", fromlist=["x"]).ART_GALLERY["Cat"], "Cat")
        check("ascii: gallery art chosen + enabled", "o.o" in st.s["art_text"] and st.s["art_enabled"])

        png = Path(home, "t.png")
        pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 40, 20)
        pb.fill(0xffffffff); pb.savev(str(png), "png", [], [])
        a._load(str(png)); a._convert()
        check("ascii: image converts to text", st.s["art_name"] == "From picture" and "@" in st.s["art_text"], repr(st.s["art_text"][:20]))
        a._load(str(png))
        a._use_text(__import__("tes.core.content", fromlist=["x"]).ART_GALLERY["Cat"], "Cat")

        win._do_apply()
        rc = Path(home, ".bashrc").read_text()
        check("apply: .bashrc has our blocks and keeps user alias", "Terminal Experience Studio" in rc and "alias keepme" in rc)
        check("apply: status synced", st.sync_status() == "synced")
        check("apply: art file written", paths.art_file().exists())
        check("apply: backup recorded", st.last_backup and Path(st.last_backup).exists())
        r = subprocess.run(["bash", "--noprofile", "--rcfile", str(Path(home, ".bashrc")), "-i", "-c", "true"],
                           capture_output=True, text=True, env={**os.environ, "USER": "sam", "TERM": "xterm"})
        check("apply: real bash prints greeting + art", "Hello sam" in r.stdout and "o.o" in r.stdout, repr(r.stdout[:60]))

        win._undo(st.last_backup)
        check("undo: .bashrc restored exactly", Path(home, ".bashrc").read_text() == "alias keepme='echo hi'\n")

        s = win.pages["settings"]; s.refresh()
        check("settings: backups listed", len(backups.list_backups()) >= 1)

        c = win.pages["companion"]
        c.cmd.set_text("rm -rf /"); c._explain()
        check("companion: risky command warned", "Careful" in c.result.get_label())
        c._use_builtin()
        check("companion: greeting pack saved", len(bashconfig.read_greetings()) >= 10)

        ap = win.pages["appearance"]
        check("appearance: no terminal -> apply disabled, no crash", not ap.apply_btn.get_sensitive() or st.terminals)
        ap._preset_toggled(ap._cards["Dracula"], "Dracula") if False else ap._cards["Dracula"].set_active(True)
        check("appearance: preset applies to theme", st.s["theme"]["bg"] == "#282a36")
        ap.opacity.set_value(80)
        check("appearance: opacity slider updates theme", st.s["theme"]["opacity"] == 80)

        st.flush()
        from tes.core import settings
        check("settings persisted with 0600", paths.settings_file().stat().st_mode & 0o777 == 0o600 and settings.load()["face"] == "(⌐■_■)")
    except Exception:
        traceback.print_exc(); check("no exception in test body", False)
    GLib.timeout_add(300, app.quit)
    return False
GLib.timeout_add(800, run)
app.run([])
bad = [n for n, ok in results if not ok]
print(f"\n{len(results)-len(bad)}/{len(results)} passed"); sys.exit(1 if bad else 0)
