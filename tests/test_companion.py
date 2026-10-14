"""v1.1: tips toggle, emotion faces, roasts, shell shortcuts, assistant parsing, AI over HTTP, tes CLI, AI themes."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tes.core import ai, assistant, bashconfig, content, pack, paths, settings, themes


class Sandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = dict(os.environ)
        for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "TES_API_KEY"):
            os.environ.pop(k, None)
        os.environ["HOME"] = self.tmp.name
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._old)))
        self.home = Path(self.tmp.name)

    def S(self, **kw):
        s = settings.sanitize({})
        s.update(kw)
        return s

    def bash(self, cmd, rc=None, env=None):
        e = {**os.environ, "USER": "tester", "HOSTNAME": "box", "TERM": "xterm", **(env or {})}
        args = ["bash", "--noprofile", "--rcfile", str(rc or paths.bashrc()), "-i", "-c", cmd]
        return subprocess.run(args, capture_output=True, text=True, env=e, timeout=20)


class PackTests(Sandbox):
    def test_tips_toggle_filters_builtin_lines(self):
        with_tips = pack.greeting_lines(self.S(tips_enabled=True))
        without = pack.greeting_lines(self.S(tips_enabled=False))
        self.assertTrue(any(l.tip for l in with_tips))
        self.assertFalse(any(l.tip for l in without))
        self.assertGreater(len(without), 5)

    def test_tips_toggle_filters_ai_lines_too(self):
        pack.set_ai_greetings([{"e": "cool", "t": "Tip: use tab", "tip": True}, {"e": "happy", "t": "Hi there", "tip": False}])
        self.assertEqual([l.text for l in pack.greeting_lines(self.S(tips_enabled=False))], ["Hi there"])

    def test_ai_pack_of_only_tips_falls_back_to_friendly_lines(self):
        pack.set_ai_greetings([{"e": "cool", "t": "Tip: only tips here", "tip": True}])
        lines = pack.greeting_lines(self.S(tips_enabled=False))
        self.assertTrue(lines and not any(l.tip for l in lines))

    def test_faces_toggle_is_baked_into_rendered_file(self):
        on = pack.render_greetings(self.S(emotion_faces=True)).splitlines()[0]
        off = pack.render_greetings(self.S(emotion_faces=False)).splitlines()[0]
        self.assertTrue(on.split("\t")[0] != "")
        self.assertEqual(off.split("\t")[0], "")

    def test_face_matches_emotion(self):
        pack.set_ai_greetings([{"e": "smug", "t": "I told you so", "tip": False}])
        self.assertTrue(pack.render_greetings(self.S()).startswith(content.EMOTIONS["smug"] + "\t"))

    def test_parse_ai_lines_tolerates_sloppy_output(self):
        raw = ("1. cool | greeting | Nice to see you\n- smug | tip | Tip: use grep -r\n"
               "excited | Another one!\nplain line without format\nnotanemotion | x | y\n\n| | |\n")
        got = pack.parse_ai_lines(raw, "greetings")
        texts = {g["t"]: g for g in got}
        self.assertIn("Nice to see you", texts)
        self.assertTrue(texts["Tip: use grep -r"]["tip"])
        self.assertEqual(texts["Nice to see you"]["e"], "cool")
        self.assertIn("plain line without format", texts)
        self.assertNotIn("y", texts)

    def test_parse_roasts_requires_placeholder_and_strips_escapes(self):
        raw = "smug | '{cmd}' is nonsense\ndead | no placeholder here\nangry | \x1b[31m{cmd}\x1b[0m!!"
        got = pack.parse_ai_lines(raw, "roasts")
        self.assertEqual(len(got), 2)
        self.assertTrue(all("\x1b" not in g["t"] for g in got))

    def test_roast_levels_are_distinct_and_all_have_placeholder(self):
        for lvl, lines in content.ROAST_LEVELS.items():
            self.assertGreaterEqual(len(lines), 8, lvl)
            self.assertGreaterEqual(sum("{cmd}" in t for _e, t in lines) / len(lines), 0.75, lvl)
            self.assertTrue(all(e in content.EMOTIONS for e, _t in lines), lvl)

    def test_ai_roasts_only_used_for_their_level(self):
        pack.set_ai_roasts([{"e": "dead", "t": "custom {cmd} roast", "tip": False}], "Unhinged")
        self.assertIn("custom {cmd} roast", [l.text for l in pack.roast_lines(self.S(roast_level="Unhinged"))])
        self.assertNotIn("custom {cmd} roast", [l.text for l in pack.roast_lines(self.S(roast_level="Spicy"))])

    def test_legacy_v1_greetings_file_is_adopted(self):
        paths.config_dir().mkdir(parents=True)
        paths.greetings_file().write_text("Tip: old line\nHello from v1\n")
        got = pack.greeting_lines(self.S())
        self.assertEqual({l.text for l in got}, {"Tip: old line", "Hello from v1"})


class ShellTests(Sandbox):
    def apply(self, **kw):
        return bashconfig.apply(self.S(**kw))

    def test_all_blocks_are_valid_bash(self):
        t = bashconfig.render_bashrc("", self.S(roast_mistakes=True, shell_shortcuts=True, greeting_pack=True))
        self.assertEqual(subprocess.run(["bash", "-n"], input=t, text=True, capture_output=True).returncode, 0)

    def test_roast_fires_on_unknown_command_and_original_message_survives(self):
        self.apply(roast_mistakes=True, roast_level="Unhinged", enabled=False)
        r = self.bash("gti status")
        self.assertEqual(r.returncode, 127)
        self.assertIn("gti", r.stderr)
        self.assertRegex(r.stderr, r"\n?.*(not found|command)")           # standard failure message still there
        texts = [t.replace("{cmd}", "gti") for _e, t in content.ROAST_LEVELS["Unhinged"]]
        self.assertTrue(any(t in r.stderr for t in texts), r.stderr)

    def test_roast_only_in_interactive_shells_and_not_for_known_commands(self):
        self.apply(roast_mistakes=True, enabled=False)
        err = self.bash("true; ls /").stderr
        for lvl in content.ROAST_LEVELS.values():
            for _e, t in lvl:
                self.assertNotIn(t[:12], err)
        non = subprocess.run(["bash", "--noprofile", "--rcfile", str(paths.bashrc()), "-c", "nonexistent_cmd_xyz"],
                             capture_output=True, text=True)   # non-interactive: no roast, normal failure
        self.assertEqual(non.returncode, 127)
        for lvl in content.ROAST_LEVELS.values():
            for _e, t in lvl:
                self.assertNotIn(t[:12], non.stderr)

    def test_roast_wraps_ubuntu_handler_instead_of_replacing_it(self):
        rc = self.home / "rc"
        rc.write_text("command_not_found_handle() { echo \"UBUNTU-HINT for $1\" >&2; return 127; }\n")
        text = bashconfig.render_bashrc(rc.read_text(), self.S(roast_mistakes=True, enabled=False))
        rc.write_text(text)
        paths.config_dir().mkdir(parents=True, exist_ok=True)
        paths.roasts_file().write_text("\tROASTED {cmd}\n")
        r = self.bash("nopenope", rc=rc)
        self.assertIn("ROASTED nopenope", r.stderr)
        self.assertIn("UBUNTU-HINT for nopenope", r.stderr)
        self.assertLess(r.stderr.index("ROASTED"), r.stderr.index("UBUNTU-HINT"))

    def test_sourcing_twice_does_not_recurse(self):
        self.apply(roast_mistakes=True, enabled=False)
        r = self.bash(f'source "{paths.bashrc()}"; source "{paths.bashrc()}"; zzznope')
        self.assertEqual(r.returncode, 127)
        self.assertNotIn("maximum", r.stderr.lower())

    def test_hostile_command_names_are_printed_literally_not_executed(self):
        self.apply(roast_mistakes=True, enabled=False)
        paths.roasts_file().write_text("\tROAST {cmd}\n")
        r = self.bash("'$(touch PWNED)&\\1'; '`touch PWNED2`'")
        self.assertEqual([p.name for p in self.home.iterdir() if p.name.startswith("PWNED")], [])
        self.assertIn("ROAST $(touch PWNED)&\\1", r.stderr)      # '&' must not expand to the pattern (bash 5.2)

    def test_roast_escape_sequences_in_command_name_are_stripped(self):
        self.apply(roast_mistakes=True, enabled=False)
        paths.roasts_file().write_text("\tROAST {cmd}\n")
        r = self.bash("$'\\e[2Jevil'")
        self.assertNotIn("\x1b[2J", r.stderr)

    def test_roast_file_removed_when_switched_off(self):
        self.apply(roast_mistakes=True)
        self.assertTrue(paths.roasts_file().exists())
        self.apply(roast_mistakes=False)
        self.assertFalse(paths.roasts_file().exists())
        self.assertNotIn("command_not_found_handle", paths.bashrc().read_text())

    def test_faces_off_prints_text_only(self):
        self.apply(roast_mistakes=True, emotion_faces=False, enabled=False, roast_level="Gentle teasing")
        r = self.bash("gti")
        face_chars = "".join(content.EMOTIONS.values())
        self.assertFalse(any(ch in r.stderr for ch in "•◕■⊙✖≧"), r.stderr)
        self.assertTrue(face_chars)

    def test_greeting_line_uses_face_and_respects_tips_toggle(self):
        pack.set_ai_greetings([{"e": "cool", "t": "Tip: only a tip", "tip": True}, {"e": "smug", "t": "Just friendly", "tip": False}])
        self.apply(greeting_pack=True, tips_enabled=False, show_date=False, greeting="Hi")
        out = self.bash("true").stdout
        self.assertIn("Just friendly", out); self.assertIn(content.EMOTIONS["smug"], out); self.assertNotIn("only a tip", out)

    def test_shortcuts_define_functions_but_never_replace_existing_commands(self):
        self.apply(shell_shortcuts=True, enabled=False)
        self.assertTrue(paths.tes_bin().exists() and os.access(paths.tes_bin(), os.X_OK))
        r = self.bash("type -t ask reply howto fix tes")
        self.assertEqual(r.stdout.split(), ["function"] * 5)
        rc = self.home / "rc2"
        rc.write_text("ask() { echo MINE; }\n" + bashconfig.render_bashrc("", self.S(shell_shortcuts=True, enabled=False)))
        self.assertIn("MINE", self.bash("ask", rc=rc).stdout)

    def test_shortcuts_removed_cleanly(self):
        self.apply(shell_shortcuts=True)
        self.apply(shell_shortcuts=False)
        self.assertFalse(paths.tes_bin().exists())
        self.assertNotIn("_TES_BIN", paths.bashrc().read_text())

    def test_status_notices_stale_side_files(self):
        s = self.S(roast_mistakes=True)
        bashconfig.apply(s)
        self.assertEqual(bashconfig.status(s), "synced")
        paths.roasts_file().write_text("\tstale\n")
        self.assertEqual(bashconfig.status(s), "pending")
        self.assertEqual(bashconfig.status(self.S(roast_mistakes=True, roast_level="Unhinged")), "pending")
        self.assertEqual(bashconfig.status(self.S(roast_mistakes=True, tips_enabled=False, greeting_pack=True)), "pending")

    def test_remove_all_clears_companion_block(self):
        self.apply(roast_mistakes=True, shell_shortcuts=True)
        bashconfig.remove_all()
        self.assertNotIn("Terminal Experience Studio", paths.bashrc().read_text())

    def test_fix_function_passes_exit_code_and_last_command(self):
        self.apply(shell_shortcuts=True, enabled=False)
        stub = self.home / "stub"; stub.write_text('#!/usr/bin/env bash\necho "ARGS: $*" > "$HOME/fix_args"\n'); stub.chmod(0o755)
        rc = self.home / "rc3"
        rc.write_text(bashconfig.render_bashrc("", self.S(shell_shortcuts=True, enabled=False)).replace(
            'if [[ -x $_TES_BIN ]]', f'_TES_BIN={stub}\n  if [[ -x $_TES_BIN ]]'))
        # drive a real interactive shell over a pty so history and $? behave like a terminal
        import pty
        pid, fd = pty.fork()
        if pid == 0:
            os.execvpe("bash", ["bash", "--noprofile", "--rcfile", str(rc), "-i"], {**os.environ, "HOME": str(self.home), "TERM": "dumb"})
        os.write(fd, b"ls /definitely/not/here 2>/dev/null\nfix\nexit\n")
        import time; time.sleep(1.5)
        try:
            os.read(fd, 65536)
        except OSError:
            pass
        os.waitpid(pid, 0)
        got = (self.home / "fix_args").read_text()
        self.assertIn("fix 2", got); self.assertIn("ls /definitely/not/here", got)


class AssistantTests(Sandbox):
    def test_parse_reply_extracts_emotion_text_and_commands(self):
        r = assistant.parse_reply("[smug] You could just use cp.\nCMD: cp a.txt b.txt\nCMD: cat a.txt > b.txt")
        self.assertEqual((r.emotion, r.text), ("smug", "You could just use cp."))
        self.assertEqual(r.commands, ["cp a.txt b.txt", "cat a.txt > b.txt"])

    def test_parse_reply_flags_dangerous_commands(self):
        r = assistant.parse_reply("[happy] Sure!\nCMD: sudo rm -rf /\nCMD: ls")
        self.assertIn("sudo rm -rf /", r.warnings)
        self.assertNotIn("ls", r.warnings)

    def test_parse_reply_handles_fences_markdown_unknown_tags_and_control_chars(self):
        r = assistant.parse_reply("[wibble] **Do** `this`:\n```\n$ ls -la\n```\x1b[31m")
        self.assertEqual(r.emotion, "happy")
        self.assertEqual(r.commands, ["ls -la"])
        self.assertNotIn("**", r.text); self.assertNotIn("\x1b", r.text)

    def test_faces_off_ignores_emotion(self):
        self.assertEqual(assistant.parse_reply("[angry] no", faces=False).emotion, "happy")

    def test_system_prompt_reflects_settings(self):
        p = assistant.system_prompt(self.S(personality="Unhinged", emotion_faces=True, name="Gremlin"))
        self.assertIn("Gremlin", p); self.assertIn("no slurs", p); self.assertIn("square brackets", p)
        self.assertNotIn("square brackets", assistant.system_prompt(self.S(emotion_faces=False)))
        self.assertIn("never claim you ran", assistant.system_prompt(self.S()).lower())

    def test_convo_memory_roundtrip_private_and_capped(self):
        assistant.save_convo([{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(30)])
        got = assistant.load_convo()
        self.assertEqual(len(got), assistant.MAX_TURNS)
        self.assertEqual(paths.convo_file().stat().st_mode & 0o777, 0o600)
        assistant.clear_convo(); self.assertEqual(assistant.load_convo(), [])

    def test_key_resolution_and_readiness(self):
        s = self.S(ai_enabled=True, provider="Groq")
        self.assertIsNotNone(assistant.readiness(s, ""))
        os.environ["TES_API_KEY"] = "abc"
        self.assertEqual(assistant.resolve_key(s), "abc")
        self.assertIsNone(assistant.readiness(s, "abc"))
        self.assertIsNone(assistant.readiness(self.S(ai_enabled=True, provider="Ollama (on this computer)"), ""))
        self.assertIn("switched off", assistant.readiness(self.S(ai_enabled=False), "abc"))

    def test_theme_parsing_validates(self):
        base = themes.DEFAULT_THEME
        good = json.dumps({"name": "Forest", "fg": "#e0f0d0", "bg": "#101a12", "cursor": "#a0ff80",
                           "palette": ["#101a12", "#d06060", "#60c060", "#d0c060", "#6090d0", "#b070d0", "#60c0b0", "#e0f0d0"] * 2})
        t = assistant.parse_theme("Sure! here:\n" + good + "\nenjoy", base)
        self.assertEqual((t.name, t.bg, t.font), ("Forest", "#101a12", base.font))
        for bad in ("no json", "{\"fg\": \"red\"}", json.dumps({**json.loads(good), "palette": ["#000000"]}),
                    json.dumps({**json.loads(good), "fg": "#222222", "bg": "#252525"})):   # last: unreadable contrast
            with self.assertRaises(assistant.ThemeGenError, msg=bad):
                assistant.parse_theme(bad, base)

    def test_settings_migration_of_retired_model_and_new_defaults(self):
        s = settings.sanitize({"model": "llama-3.3-70b-versatile", "roast_level": "nonsense"})
        self.assertEqual(s["model"], "openai/gpt-oss-120b"); self.assertEqual(s["roast_level"], "Spicy")
        self.assertTrue(s["tips_enabled"] and s["emotion_faces"]); self.assertFalse(s["roast_mistakes"])
        self.assertIn("Unhinged", content.PERSONALITIES)


# ----------------------------------------------------------------------- fake AI server on a real socket
class _Handler(BaseHTTPRequestHandler):
    seen: list = []
    mode = "ok"

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Handler.seen.append({"ua": self.headers.get("User-Agent"), "auth": self.headers.get("Authorization"), "body": body})
        if _Handler.mode == "cloudflare":
            self._send(403, "error code: 1010")
        elif _Handler.mode == "badkey":
            self._send(401, json.dumps({"error": "invalid api key"}))
        elif _Handler.mode == "empty":
            self._send(200, json.dumps({"choices": [{"message": {"content": ""}}]}))
        elif "colour themes" in body["messages"][0]["content"]:
            theme = {"name": "Neon Test", "fg": "#e8f0ff", "bg": "#0a0f1e", "cursor": "#ff4fd8",
                     "palette": ["#0a0f1e", "#ff5c8a", "#4fffb0", "#ffe14f", "#4f9bff", "#c44fff", "#4ff0ff", "#e8f0ff"] * 2}
            self._send(200, json.dumps({"choices": [{"message": {"content": "Here you go:\n" + json.dumps(theme)}}]}))
        elif "emotion | kind | text" in body["messages"][-1]["content"]:
            text = "smug | greeting | Fresh AI greeting one\ncool | tip | Tip: AI tip about grep\nlaugh | greeting | Fresh AI greeting two\nhappy | greeting | Fresh AI greeting three"
            self._send(200, json.dumps({"choices": [{"message": {"content": text}}]}))
        elif "emotion | text" in body["messages"][-1]["content"]:
            text = "dead | AI roast: {cmd} is imaginary\nsmug | AI roast: nice try with {cmd}\nangry | AI roast: {cmd}?! really?"
            self._send(200, json.dumps({"choices": [{"message": {"content": text}}]}))
        else:
            last = body["messages"][-1]["content"]
            n_user = sum(1 for m in body["messages"] if m["role"] == "user")
            text = f"[smug] Heard '{last[:40]}' (turn {n_user}).\nCMD: cp notes.txt backup.txt\nCMD: sudo rm -rf /"
            self._send(200, json.dumps({"choices": [{"message": {"content": text}}]}))

    def _send(self, code, text):
        data = text.encode()
        self.send_response(code); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


class NetworkTests(Sandbox):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 11434), _Handler)   # the Ollama default endpoint
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def setUp(self):
        super().setUp()
        _Handler.seen.clear(); _Handler.mode = "ok"
        self.prov = "Ollama (on this computer)"

    def test_request_has_user_agent_and_error_messages_are_specific(self):
        ai.chat(self.prov, "m", "", "sys", "hi")
        self.assertTrue(_Handler.seen[0]["ua"].startswith("fun-cli/"))
        for mode, needle in (("cloudflare", "firewall"), ("badkey", "rejected the API key"), ("empty", "empty reply")):
            _Handler.mode = mode
            with self.assertRaises(ai.AIError) as cm:
                ai.chat(self.prov, "m", "", "sys", "hi")
            self.assertIn(needle, str(cm.exception), mode)

    def test_cloudflare_block_is_not_reported_as_bad_key(self):
        self.assertNotIn("key", ai._explain_http_error(403, "error code: 1010").lower().replace("a bad key", ""))

    def test_groq_gpt_oss_gets_low_reasoning_and_headroom(self):
        old = ai.PROVIDERS["Groq"]["endpoint"]
        ai.PROVIDERS["Groq"]["endpoint"] = "http://127.0.0.1:11434/v1/chat/completions"
        self.addCleanup(lambda: ai.PROVIDERS["Groq"].update(endpoint=old))
        ai.chat("Groq", "openai/gpt-oss-120b", "k", "s", "u", max_tokens=60)
        b = _Handler.seen[0]["body"]
        self.assertEqual(b["reasoning_effort"], "low"); self.assertGreaterEqual(b["max_tokens"], 600)
        self.assertEqual(_Handler.seen[0]["auth"], "Bearer k")

    def cli(self, *args):
        paths.config_dir().mkdir(parents=True, exist_ok=True)
        s = self.S(ai_enabled=True, provider=self.prov, model="m")
        settings.save(s)
        return subprocess.run([sys.executable, "-m", "tes.cli", *args], cwd=ROOT, capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": str(ROOT)}, timeout=30)

    def test_cli_ask_then_reply_continues_the_conversation(self):
        r1 = self.cli("ask", "how", "do", "I", "copy", "a", "file")
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertIn(content.EMOTIONS["smug"], r1.stdout)
        self.assertIn("$ cp notes.txt backup.txt", r1.stdout)
        self.assertIn("Nothing was run", r1.stdout)
        r2 = self.cli("reply", "ok then you give me the command yourself!")
        self.assertIn("(turn 2)", r2.stdout)                      # the model saw the earlier turn
        sent = _Handler.seen[-1]["body"]["messages"]
        self.assertEqual([m["role"] for m in sent], ["system", "user", "assistant", "user"])
        self.assertIn("copy a file", sent[1]["content"])

    def test_cli_warns_about_dangerous_suggestions(self):
        out = self.cli("howto", "wipe", "everything").stdout
        self.assertIn("sudo rm -rf /", out)
        self.assertRegex(out, r"! .*(delete|whole system|home)")

    def test_cli_ask_starts_fresh_and_cmd_mode_uses_cmd_prompt(self):
        self.cli("ask", "one"); self.cli("ask", "two")
        self.assertEqual(sum(1 for m in _Handler.seen[-1]["body"]["messages"] if m["role"] == "user"), 1)
        self.cli("cmd", "list files")
        self.assertIn("task", _Handler.seen[-1]["body"]["messages"][0]["content"])

    def test_cli_fix_sends_command_and_exit_code(self):
        self.cli("fix", "127", "gti", "status")
        sent = _Handler.seen[-1]["body"]["messages"][-1]["content"]
        self.assertIn("gti status", sent); self.assertIn("127", sent)
        self.assertIn("nothing to fix", self.cli("fix", "0", "ls").stdout)

    def test_cli_explain_is_offline_for_known_commands(self):
        n = len(_Handler.seen)
        out = self.cli("explain", "rm", "-rf", "/").stdout
        self.assertIn("deletes", out); self.assertEqual(len(_Handler.seen), n)

    def test_cli_refuses_politely_when_ai_off(self):
        paths.config_dir().mkdir(parents=True, exist_ok=True)
        settings.save(self.S(ai_enabled=False))
        r = subprocess.run([sys.executable, "-m", "tes.cli", "ask", "hi"], cwd=ROOT, capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": str(ROOT)})
        self.assertEqual(r.returncode, 1); self.assertIn("switched off", r.stderr)

    def test_cli_reports_network_errors_without_traceback(self):
        _Handler.mode = "cloudflare"
        r = self.cli("ask", "hi")
        self.assertEqual(r.returncode, 2); self.assertIn("firewall", r.stderr); self.assertNotIn("Traceback", r.stderr)

    def test_generated_greetings_pipeline(self):
        class H(_Handler):
            pass
        _Handler.mode = "ok"
        sys_p, user_p = pack.greetings_prompt(self.S(tips_enabled=False, personality="Unhinged"))
        self.assertIn("Do NOT include Linux tips", user_p); self.assertIn("emotion | kind | text", user_p)
        rs, ru = pack.roast_prompt(self.S(roast_level="Unhinged"))
        self.assertIn("{cmd}", ru); self.assertIn("no slurs", rs)


if __name__ == "__main__":
    unittest.main()
