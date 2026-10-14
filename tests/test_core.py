import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tes.core import (asciiart, backups, bashconfig, content, explain, pack, paths, prompts, settings,
                      shellblock, themes)


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = dict(os.environ)
        for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME"):
            os.environ.pop(k, None)
        os.environ["HOME"] = self.tmp.name
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._old)))
        self.home = Path(self.tmp.name)

    def S(self, **kw):
        s = settings.sanitize({})
        s.update(kw)
        return s


class ShellBlockTests(unittest.TestCase):
    A, B = "# >>> x >>>", "# <<< x <<<"

    def test_insert_replace_remove_roundtrip(self):
        base = "alias a=b\nexport X=1\n"
        t1 = shellblock.set_block(base, self.A, self.B, f"{self.A}\none\n{self.B}")
        self.assertTrue(t1.startswith(base.rstrip()))
        t2 = shellblock.set_block(t1, self.A, self.B, f"{self.A}\ntwo\n{self.B}")
        self.assertIn("two", t2); self.assertNotIn("one", t2)
        self.assertEqual(t2.count(self.A), 1)
        t3 = shellblock.set_block(t2, self.A, self.B, None)
        self.assertEqual(t3.strip(), base.strip())

    def test_damaged_markers_raise_instead_of_corrupting(self):
        with self.assertRaises(shellblock.BlockError):
            shellblock.set_block(f"x\n{self.A}\nunfinished\n", self.A, self.B, f"{self.A}\nn\n{self.B}")
        with self.assertRaises(shellblock.BlockError):
            shellblock.set_block(f"{self.A}\n{self.B}\n{self.A}\n{self.B}\n", self.A, self.B, None)


class ThemeTests(unittest.TestCase):
    def test_presets_are_valid(self):
        for t in themes.PRESETS.values():
            self.assertEqual(len(t.palette), 16)
            themes.from_dict(t.to_dict())

    def test_roundtrip_and_rejects_garbage(self):
        t = themes.PRESETS["Nord"]
        self.assertEqual(themes.loads(themes.dumps(t)), t)
        for bad in ('{"fg": "red"}', '{"palette": ["#000000"]}', '[1,2]', 'nope', '{"font": "a\\"b"}', '{"cursor_shape":"x"}'):
            with self.assertRaises(themes.ThemeError, msg=bad):
                themes.loads(bad)

    def test_clamps(self):
        t = themes.from_dict({"opacity": 5, "font_size": 999})
        self.assertEqual((t.opacity, t.font_size), (30, 48.0))

    def test_nearest_256(self):
        self.assertEqual(themes.nearest_256("#000000"), 16)
        self.assertEqual(themes.nearest_256("#ffffff"), 231)


class SettingsTests(Sandbox):
    def test_legacy_file_is_migrated(self):
        paths.config_dir().mkdir(parents=True)
        paths.settings_file().write_text(json.dumps({
            "greeting": "Welcome back, {user}!", "face": "(⌐■_■)", "prompt_style": "Keep my existing prompt",
            "ai_greeting": True, "accent": "not-a-colour", "show_date": "yes"}))
        s = settings.load()
        self.assertEqual(s["greeting"], "Welcome back, {user}!")
        self.assertEqual(s["face"], "(⌐■_■)")
        self.assertEqual(s["prompt_preset"], "keep")
        self.assertTrue(s["greeting_pack"])
        self.assertEqual(s["accent"], "#7bd88f")   # invalid -> default
        self.assertIs(s["show_date"], True)         # wrong type -> default

    def test_save_is_private(self):
        settings.save(settings.load())
        self.assertEqual(paths.settings_file().stat().st_mode & 0o777, 0o600)


class BashTests(Sandbox):
    def run_bash(self, rc: str, cmd: str = "true", interactive=True):
        env = {**os.environ, "HOME": str(self.home), "USER": "tester", "HOSTNAME": "box", "TERM": "xterm"}
        args = ["bash", "--noprofile", "--rcfile", str(rc)] + (["-i"] if interactive else [])
        return subprocess.run(args + ["-c", cmd], capture_output=True, text=True, env=env, timeout=20)

    def apply(self, **kw):
        return bashconfig.apply(self.S(**kw))

    def test_generated_blocks_are_valid_bash_for_every_preset(self):
        for p in prompts.PRESETS:
            for git in (True, False):
                for clock in (True, False):
                    s = self.S(prompt_preset=p.id, prompt_git=git, prompt_time=clock, fastfetch=True, show_host=True,
                               greeting_pack=True, art_enabled=True, art_text="x", custom_motd="a\nb")
                    text = bashconfig.render_bashrc("", s)
                    r = subprocess.run(["bash", "-n"], input=text, capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, f"{p.id}: {r.stderr}")

    def test_apply_preserves_user_content_and_is_idempotent(self):
        original = "# my stuff\nalias gs='git status'\nexport PATH=$HOME/bin:$PATH\n"
        paths.bashrc().write_text(original)
        self.apply(prompt_preset="minimal")
        first = paths.bashrc().read_text()
        self.assertTrue(first.startswith(original.rstrip()))
        self.apply(prompt_preset="minimal")
        self.assertEqual(paths.bashrc().read_text(), first)
        self.assertEqual(bashconfig.status(self.S(prompt_preset="minimal")), "synced")
        self.assertEqual(bashconfig.status(self.S(prompt_preset="classic")), "pending")

    def test_backup_and_undo(self):
        original = "alias a=b\n"
        paths.bashrc().write_text(original)
        rep = self.apply()
        self.assertTrue(rep.backup and rep.backup.exists())
        self.assertNotEqual(paths.bashrc().read_text(), original)
        backups.restore(backups.entry_for(rep.backup))
        self.assertEqual(paths.bashrc().read_text(), original)

    def test_undo_when_bashrc_did_not_exist(self):
        rep = self.apply()
        self.assertTrue(paths.bashrc().exists())
        backups.restore(backups.entry_for(rep.backup))
        self.assertFalse(paths.bashrc().exists())

    def test_remove_all_leaves_user_content(self):
        paths.bashrc().write_text("alias a=b\n")
        self.apply(prompt_preset="classic")
        bashconfig.remove_all()
        self.assertEqual(paths.bashrc().read_text().strip(), "alias a=b")

    def test_symlinked_bashrc_stays_a_symlink(self):
        real = self.home / "dotfiles" / "bashrc"
        real.parent.mkdir()
        real.write_text("alias a=b\n")
        paths.bashrc().symlink_to(real)
        self.apply()
        self.assertTrue(paths.bashrc().is_symlink())
        self.assertIn("Terminal Experience Studio", real.read_text())

    def test_damaged_markers_abort_without_touching_anything(self):
        broken = f"alias a=b\n{bashconfig.MOTD_START}\nhalf done\n"
        paths.bashrc().write_text(broken)
        with self.assertRaises(shellblock.BlockError):
            self.apply()
        self.assertEqual(paths.bashrc().read_text(), broken)

    def test_greeting_runs_and_substitutes(self):
        self.apply(greeting="Good {daypart}, {user} on {host}!", face="(•‿•)", show_date=False)
        r = self.run_bash(paths.bashrc())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"Good (morning|afternoon|evening|night), tester on box!")
        self.assertIn("(•‿•)", r.stdout)

    def test_nothing_printed_in_non_interactive_shells(self):
        self.apply()
        r = self.run_bash(paths.bashrc(), interactive=False)
        self.assertEqual(r.stdout, "")

    def test_hostile_text_is_never_executed(self):
        evil = "$(touch PWNED) `touch PWNED2` '; touch PWNED3; echo '\"; touch PWNED4 #"
        self.apply(greeting=evil, custom_motd=evil, face=evil, name=evil)
        self.run_bash(paths.bashrc())
        self.assertEqual([p.name for p in self.home.iterdir() if p.name.startswith("PWNED")], [])
        r = self.run_bash(paths.bashrc())
        self.assertIn("$(touch PWNED)", r.stdout)  # shown literally

    def test_escape_sequences_are_stripped(self):
        self.apply(greeting="hi\x1b[31mred", custom_motd="a\x07b")
        text = paths.bashrc().read_text()
        self.assertNotIn("\x1b", text); self.assertNotIn("\x07", text)

    def test_art_and_greeting_pack(self):
        pack.set_ai_greetings([{"e": "cool", "t": "Tip one\x1b[2J", "tip": True}, {"e": "happy", "t": "Hello pal", "tip": False}])
        self.apply(art_enabled=True, art_text=" /\\_/\\\n( o.o )", greeting_pack=True, show_date=False)
        r = self.run_bash(paths.bashrc())
        self.assertIn("( o.o )", r.stdout)
        self.assertRegex(r.stdout, r"Tip one|Hello pal")
        self.assertNotIn("\x1b[2J", r.stdout)

    def test_disabled_greeting_prints_nothing(self):
        self.apply(enabled=False)
        self.assertEqual(self.run_bash(paths.bashrc()).stdout, "")

    def test_ps1_presets_produce_prompts_and_react_to_exit_code(self):
        for pid in ("minimal", "classic", "two_line"):
            self.apply(prompt_preset=pid, prompt_time=True, enabled=False)
            ok = self.run_bash(paths.bashrc(), 'eval "$PROMPT_COMMAND"; printf %s "$PS1"')
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("\\[", ok.stdout)
            if pid == "classic":
                continue  # classic has no status symbol by design
            bad = self.run_bash(paths.bashrc(), 'false; eval "$PROMPT_COMMAND"; printf %s "$PS1"')
            self.assertIn("[31m", bad.stdout)   # red symbol after failure
            self.assertIn("[32m", ok.stdout)    # green after success

    def test_hook_is_added_only_once_when_rc_sourced_twice(self):
        self.apply(prompt_preset="minimal", enabled=False)
        r = self.run_bash(paths.bashrc(), f'source "{paths.bashrc()}"; printf %s "$PROMPT_COMMAND"')
        self.assertEqual(r.stdout.split(";").count("_tes_set_prompt"), 1)

    def test_git_branch_name_cannot_inject_code(self):
        repo = self.home / "repo"
        repo.mkdir()
        env = {**os.environ, "GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@a", "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@a"}
        subprocess.run("git init -q . && git commit -q --allow-empty -m x && git branch '$(touch${IFS}INJECTED)' && git checkout -q '$(touch${IFS}INJECTED)'",
                       shell=True, cwd=repo, env=env, check=True, capture_output=True)
        self.apply(prompt_preset="classic", enabled=False)
        # Bash expands PS1 with promptvars; expand it the same way here.
        r = self.run_bash(paths.bashrc(), f'cd "{repo}"; eval "$PROMPT_COMMAND"; echo "${{PS1@P}}"')
        self.assertIn("(", r.stdout)  # the branch is shown, sanitised
        self.assertNotIn("$(", r.stdout)
        self.assertFalse((repo / "INJECTED").exists())
        self.assertFalse((self.home / "INJECTED").exists())

    def test_existing_prompt_command_array_and_string(self):
        self.apply(prompt_preset="minimal", enabled=False)
        r = self.run_bash(paths.bashrc(), 'true')  # string case runs without error
        self.assertEqual(r.returncode, 0, r.stderr)
        text = bashconfig.render_bashrc("PROMPT_COMMAND=(echo_hi)\n", self.S(prompt_preset="minimal", enabled=False))
        r = self.run_bash(self._write(text), 'declare -p PROMPT_COMMAND')
        self.assertIn("_tes_set_prompt", r.stdout)
        self.assertIn("echo_hi", r.stdout)

    def _write(self, text):
        p = self.home / "rc_test"
        p.write_text(text)
        return p

    def test_starship_uses_own_config_and_never_touches_users(self):
        users = paths.config_home() / "starship.toml"
        users.parent.mkdir(parents=True, exist_ok=True)
        users.write_text("# mine\n")
        self.apply(prompt_preset="starship_two_line", prompt_time=True)
        self.assertEqual(users.read_text(), "# mine\n")
        self.assertTrue(paths.starship_file().exists())
        import tomllib
        tomllib.loads(paths.starship_file().read_text())  # must be valid TOML
        self.assertIn("STARSHIP_CONFIG", paths.bashrc().read_text())
        self.apply(prompt_preset="keep")
        self.assertFalse(paths.starship_file().exists())


class AsciiTests(unittest.TestCase):
    def test_brightness_maps_to_density(self):
        # 4 grey pixels: black, dark, light, white (RGB, no alpha)
        data = bytes([0, 0, 0, 85, 85, 85, 170, 170, 170, 255, 255, 255])
        out = asciiart.pixels_to_ascii(data, 4, 1, 12, 3, False, "Classic")
        self.assertEqual(out[0], " ")            # black -> empty
        self.assertEqual(out[-1], "@")           # white -> densest
        self.assertEqual(len(out), 4)
        inv = asciiart.pixels_to_ascii(data, 4, 1, 12, 3, False, "Classic", invert=True)
        self.assertEqual(inv[0], "@")

    def test_transparent_pixels_become_spaces(self):
        # RGBA: fully transparent white, then opaque white
        data = bytes([255, 255, 255, 0, 255, 255, 255, 255])
        self.assertEqual(asciiart.pixels_to_ascii(data, 2, 1, 8, 4, True), " @")

    def test_trailing_blank_rows_are_trimmed(self):
        data = bytes([255, 255, 255, 0, 0, 0])  # row 1 white, row 2 black
        self.assertEqual(asciiart.pixels_to_ascii(data, 1, 2, 3, 3, False), "@")

    def test_size_keeps_aspect(self):
        self.assertEqual(asciiart.target_size(100, 100, 60), (60, 30))


class ExplainTests(unittest.TestCase):
    def test_known_and_unknown(self):
        self.assertTrue(explain.explain("ls -lah").known)
        self.assertFalse(explain.explain("frobnicate --now").known)

    def test_sudo_and_risk(self):
        self.assertTrue(any("administrator" in w for w in explain.explain("sudo apt update").warnings))
        self.assertTrue(explain.explain("rm -rf /").warnings)
        self.assertTrue(explain.explain("curl https://x.sh | sudo bash").warnings)
        self.assertTrue(explain.explain("dd if=a.iso of=/dev/sda").warnings)
        self.assertTrue(explain.explain(":(){ :|:& };:").warnings)


class ContentTests(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(content.clean_line("a\x1b[0mb\n"), "a[0mb")
        self.assertEqual(content.clean_art("\n\n a\n  b  \n\n"), " a\n  b")

    def test_pack_parser(self):
        from tes.core import ai
        raw = "1. Hello there\n- Tip: use Tab\n\n\"Hello there\"\nok\n* Another one here"
        self.assertEqual(ai.parse_pack(raw), ["Hello there", "Tip: use Tab", "Another one here"])


if __name__ == "__main__":
    unittest.main()
