"""AI Companion: behaviour, roasts, chat, command helper, explainer, provider.

Everything except the AI-writing buttons works offline. The AI never runs anything:
commands it suggests are shown with risk warnings and a Copy button.
"""
from __future__ import annotations

import random
import webbrowser

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ...core import ai, assistant, content, explain, pack
from ..common import Page, combo_row, group, label, run_async
from ..widgets import TerminalPreview

PROVIDER_NAMES = list(ai.PROVIDERS)
PERSONA_NAMES = list(content.PERSONALITIES)
LEVELS = list(content.ROAST_LEVELS)


class CompanionPage(Page):
    page_id = "companion"
    title = "AI Companion"
    subtitle = "Give your terminal a personality. Everything works offline; AI is an optional upgrade."
    icon = "tes-companion-symbolic"

    def __init__(self, win):
        super().__init__(win)
        s = self.state.s
        self._loading = True
        self._key_timer = 0
        self.chat_hist: list[dict] = []
        self.term = TerminalPreview("companion", max_height=190, min_height=120)
        self.pin(self.term)
        self.header("Companion")

        # ---------------------------------------------------------- personality
        pg = group("Personality", "Who your terminal is. It shapes greetings, roasts, chat and explanations.")
        self.name_row = Adw.EntryRow(title="Companion name")
        self.name_row.set_text(s["name"])
        self.name_row.connect("changed", lambda r: self._opt(name=r.get_text()[:40] or "Terminal friend"))
        pg.add(self.name_row)
        self.persona = combo_row("Personality", PERSONA_NAMES, PERSONA_NAMES.index(s["personality"]) if s["personality"] in PERSONA_NAMES else 0)
        self.persona.connect("notify::selected", self._persona_changed)
        pg.add(self.persona)
        self.add(pg)
        self.unhinged_note = label("Unhinged is playful chaos: it teases your typos and bad ideas, never who you are. "
                                   "No slurs, no profanity. Roasts are pre-written, so they appear instantly and work offline.",
                                   "tes-callout", "warn")
        self.add(self.unhinged_note)

        # ---------------------------------------------------------- behaviour
        bg = group("Behaviour")
        self.tips = Adw.SwitchRow(title="Show Linux tips", subtitle="Off = only greetings and jokes, never advice.", active=s["tips_enabled"])
        self.faces = Adw.SwitchRow(title="Faces match what it says", subtitle="Happy, smug, shocked... the face follows the mood of each line.",
                                   active=s["emotion_faces"])
        self.roast = Adw.SwitchRow(title="Roast me when I mistype a command", subtitle="Mistyped commands get a reaction. Ubuntu's 'did you mean...?' hint still shows.",
                                   active=s["roast_mistakes"])
        self.level = combo_row("Roast level", LEVELS, LEVELS.index(s["roast_level"]) if s["roast_level"] in LEVELS else 1)
        self.shortcuts = Adw.SwitchRow(title="Shell shortcuts", subtitle="Adds tes, ask, reply, howto and fix. Existing commands with those names are never replaced.",
                                       active=s["shell_shortcuts"])
        self.tips.connect("notify::active", lambda r, _p: self._opt(tips_enabled=r.get_active()))
        self.faces.connect("notify::active", lambda r, _p: self._opt(emotion_faces=r.get_active()))
        self.roast.connect("notify::active", lambda r, _p: self._opt(roast_mistakes=r.get_active()))
        self.level.connect("notify::selected", lambda r, _p: self._opt(roast_level=LEVELS[r.get_selected()]))
        self.shortcuts.connect("notify::active", lambda r, _p: self._opt(shell_shortcuts=r.get_active()))
        for w in (self.tips, self.faces, self.roast, self.level, self.shortcuts):
            bg.add(w)
        self.add(bg)

        # ---------------------------------------------------------- lines (greetings + roasts)
        lg = group("Greeting and roast lines", "Written ahead of time and saved, so opening a terminal never waits on the internet.")
        self.pack_row = Adw.ActionRow(title="Greeting lines", subtitle="")
        self.builtin_btn = Gtk.Button(label="Use built-in", valign=Gtk.Align.CENTER)
        self.gen_btn = Gtk.Button(label="Write with AI", valign=Gtk.Align.CENTER)
        self.gen_btn.add_css_class("suggested-action")
        self.builtin_btn.connect("clicked", lambda _b: self._use_builtin())
        self.gen_btn.connect("clicked", lambda _b: self._generate_greetings())
        self.pack_row.add_suffix(self.builtin_btn)
        self.pack_row.add_suffix(self.gen_btn)
        lg.add(self.pack_row)
        self.roast_row = Adw.ActionRow(title="Roast lines", subtitle="")
        self.try_btn = Gtk.Button(label="Try a roast", valign=Gtk.Align.CENTER)
        self.gen_roast_btn = Gtk.Button(label="Write with AI", valign=Gtk.Align.CENTER)
        self.try_btn.connect("clicked", lambda _b: self._try_roast())
        self.gen_roast_btn.connect("clicked", lambda _b: self._generate_roasts())
        self.roast_row.add_suffix(self.try_btn)
        self.roast_row.add_suffix(self.gen_roast_btn)
        lg.add(self.roast_row)
        self.add(lg)
        self.pack_view = Gtk.Label(xalign=0, wrap=True, selectable=False)
        self.pack_view.add_css_class("tes-result")
        self.pack_view.add_css_class("tes-code")
        self.add(self.pack_view)

        # ---------------------------------------------------------- chat
        cg = group("Talk to your companion", "Ask anything, or switch to 'Find a command' and describe what you want to do. "
                                              "It only suggests; nothing is ever run for you.")
        self.mode = combo_row("Mode", ["Chat", "Find a command"], 0)
        cg.add(self.mode)
        self.add(cg)
        self.chat_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=4, margin_bottom=4)
        self.chat_scroll = Gtk.ScrolledWindow(child=self.chat_box, min_content_height=60, max_content_height=380,
                                              propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.add(self.chat_scroll)
        send_row = Gtk.Box(spacing=8)
        self.chat_entry = Gtk.Entry(hexpand=True)
        self.chat_entry.connect("activate", lambda *_: self._send())
        self.send_btn = Gtk.Button(label="Send")
        self.send_btn.add_css_class("suggested-action")
        self.send_btn.connect("clicked", lambda _b: self._send())
        self.new_btn = Gtk.Button(label="New conversation")
        self.new_btn.add_css_class("flat")
        self.new_btn.connect("clicked", lambda _b: self._new_chat())
        for w in (self.chat_entry, self.send_btn, self.new_btn):
            send_row.append(w)
        self.add(send_row)
        self._bubble_system("Say hi, or ask for a command. I remember this conversation until you start a new one.")
        GLib.idle_add(lambda: (self._fit_chat(), GLib.SOURCE_REMOVE)[1])

        # ---------------------------------------------------------- explainer
        eg = group("What does this command do?", "Common commands are explained instantly and offline; risky ones get a clear warning.")
        self.cmd = Adw.EntryRow(title="Command")
        self.cmd.connect("entry-activated", lambda *_: self._explain())
        eg.add(self.cmd)
        er = Adw.ActionRow(title="Explain it")
        self.explain_btn = Gtk.Button(label="Explain", valign=Gtk.Align.CENTER)
        self.explain_btn.add_css_class("suggested-action")
        self.explain_btn.connect("clicked", lambda _b: self._explain())
        self.ai_explain_btn = Gtk.Button(label="Ask AI for detail", valign=Gtk.Align.CENTER)
        self.ai_explain_btn.connect("clicked", lambda _b: self._explain_ai())
        er.add_suffix(self.ai_explain_btn)
        er.add_suffix(self.explain_btn)
        eg.add(er)
        self.add(eg)
        self.result = Gtk.Label(xalign=0, wrap=True, selectable=True, use_markup=True)
        self.result.add_css_class("tes-result")
        self.result.set_visible(False)
        self.add(self.result)

        # ---------------------------------------------------------- provider
        ag = group("AI provider (optional)", "Skip this and the app works exactly the same, just without AI writing.")
        self.enable = Adw.SwitchRow(title="Enable AI features", subtitle="AI is only called when you press a button or use the tes command.",
                                    active=s["ai_enabled"])
        self.enable.connect("notify::active", lambda r, _p: self._opt(ai_enabled=r.get_active()))
        ag.add(self.enable)
        self.provider = combo_row("Provider", PROVIDER_NAMES, PROVIDER_NAMES.index(s["provider"]) if s["provider"] in PROVIDER_NAMES else 0)
        self.provider.connect("notify::selected", self._provider_changed)
        ag.add(self.provider)
        self.model = Adw.EntryRow(title="Model")
        self.model.set_text(s["model"])
        self.model.connect("changed", lambda r: self._opt(model=r.get_text().strip()))
        ag.add(self.model)
        self.key = Adw.PasswordEntryRow(title="API key")
        self.key.set_text(self.state.api_key)
        self.key.connect("changed", self._key_changed)
        ag.add(self.key)
        self.remember = Adw.SwitchRow(title="Remember key in my desktop keyring",
                                      subtitle="Needed for the tes command in your terminal. Stored by your system, never in a file we write.",
                                      active=s["keyring_remember"])
        self.remember.connect("notify::active", self._remember_changed)
        ag.add(self.remember)
        br = Adw.ActionRow(title="Get a key", subtitle="Opens the provider's website in your browser.")
        self.get_btn = Gtk.Button(label="Open website", valign=Gtk.Align.CENTER)
        self.get_btn.connect("clicked", lambda _b: webbrowser.open(self._info()["url"]))
        self.test_btn = Gtk.Button(label="Test connection", valign=Gtk.Align.CENTER)
        self.test_btn.connect("clicked", lambda _b: self._test())
        br.add_suffix(self.get_btn)
        br.add_suffix(self.test_btn)
        ag.add(br)
        self.add(ag)
        self.status = label("", "tes-note")
        self.add(self.status)
        self.add(label("Privacy: your key is never written to settings or shell files. It stays in memory, or in your desktop "
                       "keyring if you switch that on.", "tes-note"))

        self._loading = False
        self._refresh()

    # ================================================================== helpers
    def _info(self) -> dict:
        return ai.PROVIDERS[PROVIDER_NAMES[self.provider.get_selected()]]

    def _ai_ready(self) -> bool:
        return assistant.readiness(self.state.s, self.state.api_key) is None

    def _opt(self, **kw) -> None:
        if self._loading:
            return
        self.state.update("companion", **kw)
        self._refresh()

    def _persona_changed(self, row, _p) -> None:
        if self._loading:
            return
        name = PERSONA_NAMES[row.get_selected()]
        kw = {"personality": name}
        if name == "Unhinged" and not self.state.s["roast_mistakes"]:
            kw.update(roast_mistakes=True, roast_level="Unhinged")
            self.win.toast("Unhinged mode on: mistyped commands will be roasted once you Apply to Bash.")
            self._loading = True
            self.roast.set_active(True)
            self.level.set_selected(LEVELS.index("Unhinged"))
            self._loading = False
        self.state.update("companion", **kw)
        self._refresh()

    def _provider_changed(self, *_) -> None:
        if self._loading:
            return
        name = PROVIDER_NAMES[self.provider.get_selected()]
        self._loading = True
        self.model.set_text(ai.PROVIDERS[name]["model"])
        key = ai.keyring_lookup(name) if self.state.s["keyring_remember"] else ""
        self.state.api_key = key
        self.key.set_text(key)
        self._loading = False
        self.state.update("companion", provider=name, model=ai.PROVIDERS[name]["model"])
        self._refresh()

    def _key_changed(self, row) -> None:
        if self._loading:
            return
        self.state.api_key = row.get_text().strip()
        if self.state.s["keyring_remember"]:  # keep the keyring in step so the tes command sees the new key
            if self._key_timer:
                GLib.source_remove(self._key_timer)
            self._key_timer = GLib.timeout_add(1200, self._store_key)
        self._refresh()

    def _store_key(self) -> bool:
        self._key_timer = 0
        if self.state.api_key and ai.keyring_available():
            provider, key = self.state.s["provider"], self.state.api_key
            run_async(lambda: ai.keyring_store(provider, key), lambda ok, err: None)
        return GLib.SOURCE_REMOVE

    def _remember_changed(self, row, _p) -> None:
        if self._loading:
            return
        on = row.get_active()
        name = self.state.s["provider"]
        if on:
            if not ai.keyring_available():
                self._loading = True
                row.set_active(False)
                self._loading = False
                self.win.alert("Keyring tool not found", "Install it with:  sudo apt install libsecret-tools\nThen switch this on again.")
                return
            if self.state.api_key and not ai.keyring_store(name, self.state.api_key):
                self.status.set_text("Couldn't save to the keyring. The key stays in memory for this session.")
        else:
            ai.keyring_clear(name)
        self.state.update("companion", keyring_remember=on)

    # ================================================================== view
    def _refresh(self) -> None:
        s = self.state.s
        info = self._info()
        self.key.set_visible(info["needs_key"])
        self.remember.set_visible(info["needs_key"])
        usable = bool(s["ai_enabled"])
        for b in (self.gen_btn, self.gen_roast_btn, self.ai_explain_btn, self.test_btn, self.send_btn):
            b.set_sensitive(usable)
        self.chat_entry.set_sensitive(usable)
        self.chat_entry.set_placeholder_text("e.g. how do I copy the contents of a file to the clipboard?" if usable
                                             else "Switch on AI features below to chat")
        self.level.set_visible(bool(s["roast_mistakes"]))
        self.unhinged_note.set_visible(s["personality"] == "Unhinged" or (s["roast_mistakes"] and s["roast_level"] == "Unhinged"))
        n_greet, n_roast = pack.ai_counts()
        self.pack_row.set_subtitle(f"{n_greet} AI-written lines saved" if n_greet else "Using the built-in lines")
        self.roast_row.set_subtitle(f"Level: {s['roast_level']}" + (f" - {n_roast} AI-written lines saved" if n_roast else " - built-in lines"))
        lines = pack.greeting_lines(s)
        faces = bool(s["emotion_faces"])
        show = [f"  {l.face + '  ' if faces else ''}{l.text}" for l in lines[:12]]
        self.pack_view.set_text("\n".join(show) + (f"\n  ... and {len(lines) - 12} more" if len(lines) > 12 else ""))
        self.term.set_accent(s["accent"])

    def _preview(self, roast: bool = False) -> None:
        s = self.state.s
        faces = bool(s["emotion_faces"])
        face, text = random.choice(pack.preview_pairs(s))
        lines = [[(f"{s['face']}  ", "accent"), (f"{s['name']} says:", "fg")],
                 ([(face + "  ", "accent")] if face else []) + [(text, "dim")]]
        if roast:
            line = random.choice(pack.roast_lines(s))
            lines += [[], [("you@zorin:~$ ", "p2"), ("gti status", "fg")],
                      ([(line.face + "  ", "accent")] if faces else []) + [(pack.roast_text(line, "gti"), "p3")],
                      [("gti: command not found", "dim")]]
        self.term.set_lines(lines, animate=True)

    # ================================================================== lines
    def _use_builtin(self) -> None:
        pack.clear_ai_greetings()
        self.state.update("companion", greeting_pack=True)
        self._refresh()
        self._preview()
        self.win.toast("Built-in lines will be used. Apply to Bash to save.")

    def _try_roast(self) -> None:
        self._preview(roast=True)

    def _generate_greetings(self) -> None:
        s = dict(self.state.s)
        system, user = pack.greetings_prompt(s)
        self.gen_btn.set_sensitive(False)
        self.status.set_text("Asking your companion to write greetings...")

        def done(raw, err):
            self._refresh()
            if err:
                self.status.set_text(str(err))
                return
            lines = pack.parse_ai_lines(raw, "greetings")
            if len(lines) < 3:
                self.status.set_text("The AI's answer wasn't usable. Try again, or use the built-in lines.")
                return
            pack.set_ai_greetings(lines)
            self.state.update("companion", greeting_pack=True)
            self.status.set_text(f"Saved {len(lines)} new lines. Apply to Bash to use them.")
            self._refresh()
            self._preview()

        run_async(lambda: ai.chat(s["provider"], s["model"], self.state.api_key, system, user, max_tokens=600, temperature=0.95), done)

    def _generate_roasts(self) -> None:
        s = dict(self.state.s)
        system, user = pack.roast_prompt(s)
        self.gen_roast_btn.set_sensitive(False)
        self.status.set_text(f"Writing fresh {s['roast_level'].lower()} roasts...")

        def done(raw, err):
            self._refresh()
            if err:
                self.status.set_text(str(err))
                return
            lines = pack.parse_ai_lines(raw, "roasts")
            if len(lines) < 3:
                self.status.set_text("The AI's answer wasn't usable. Try again.")
                return
            pack.set_ai_roasts(lines, s["roast_level"])
            self.state.update("companion", roast_mistakes=True)
            self.status.set_text(f"Saved {len(lines)} new roasts for '{s['roast_level']}'. Apply to Bash to use them.")
            self._refresh()
            self._preview(roast=True)

        run_async(lambda: ai.chat(s["provider"], s["model"], self.state.api_key, system, user, max_tokens=700, temperature=1.0), done)

    # ================================================================== chat
    def _bubble(self, kind: str, halign: Gtk.Align) -> Gtk.Box:
        box = Gtk.Box(halign=halign, spacing=12)
        box.add_css_class("tes-bubble")
        box.add_css_class(kind)
        self.chat_box.append(box)
        return box

    def _bubble_system(self, text: str) -> None:
        self._bubble("system", Gtk.Align.START).append(label(text, "tes-note", max_width_chars=70))

    def _bubble_user(self, text: str) -> None:
        lb = label(text, max_width_chars=60)
        lb.set_selectable(True)
        self._bubble("user", Gtk.Align.END).append(lb)

    def _bubble_ai(self, reply: assistant.Reply) -> None:
        box = self._bubble("assistant", Gtk.Align.START)
        if self.state.s["emotion_faces"]:
            box.append(label(reply.face, "tes-chat-face", wrap=False, valign=Gtk.Align.START))
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        if reply.text:
            t = label(reply.text, max_width_chars=64)
            t.set_selectable(True)
            col.append(t)
        for cmd in reply.commands:
            row = Gtk.Box(spacing=8)
            code = label("$ " + cmd, "tes-code", "tes-cmd", max_width_chars=58)
            code.set_selectable(True)
            code.set_hexpand(True)
            copy = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy command", valign=Gtk.Align.CENTER)
            copy.add_css_class("flat")
            copy.connect("clicked", lambda _b, c=cmd: (self.get_clipboard().set(c), self.win.toast("Command copied. Nothing was run.")))
            row.append(code)
            row.append(copy)
            col.append(row)
            for w in reply.warnings.get(cmd, []):
                col.append(label("Careful: " + w, "tes-warn", max_width_chars=64))
        box.append(col)

    def _fit_chat(self) -> None:
        """Grow the chat area with its content (up to a cap, then it scrolls). The page's own scroller only gives
        nested widgets their *minimum* height, so we set that minimum from the content ourselves."""
        width = max(300, self.chat_scroll.get_width() or 700)
        natural = self.chat_box.measure(Gtk.Orientation.VERTICAL, width)[1] + 8
        self.chat_scroll.set_min_content_height(max(80, min(380, natural)))

    def _scroll_down(self) -> None:
        def go():
            self._fit_chat()
            adj = self.chat_scroll.get_vadjustment()
            adj.set_value(adj.get_upper())
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(120, go)

    def _new_chat(self) -> None:
        self.chat_hist = []
        while (c := self.chat_box.get_first_child()):
            self.chat_box.remove(c)
        self._bubble_system("New conversation. What's up?")
        self._scroll_down()

    def _send(self) -> None:
        text = self.chat_entry.get_text().strip()
        if not text:
            return
        why = assistant.readiness(self.state.s, self.state.api_key)
        if why:
            self.win.alert("AI isn't ready", why)
            return
        mode = "cmd" if self.mode.get_selected() == 1 else "chat"
        s = dict(self.state.s)
        self.chat_entry.set_text("")
        self._bubble_user(text)
        pending = label("thinking...", "tes-note")
        self.chat_box.append(pending)
        self._scroll_down()
        self.send_btn.set_sensitive(False)
        hist = list(self.chat_hist)

        def done(res, err):
            self.chat_box.remove(pending)
            self.send_btn.set_sensitive(True)
            if err:
                self._bubble_system(str(err))
            else:
                reply, self.chat_hist = res
                self._bubble_ai(reply)
            self._scroll_down()

        run_async(lambda: assistant.ask(s, self.state.api_key, text, hist, mode), done)

    # ================================================================== explain
    def _explain(self) -> None:
        cmd = self.cmd.get_text().strip()
        if not cmd:
            return
        e = explain.explain(cmd)
        esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        out = []
        if e.known:
            out.append(f"<b>{esc(e.summary)}</b>")
            for ex, meaning in e.examples:
                out.append(f"<tt>{esc(ex)}</tt>  -  {esc(meaning)}")
        elif not e.warnings:
            out.append("I don't have this one in my offline notes." + (" Try \"Ask AI for detail\"." if self.state.s["ai_enabled"] else
                                                                     " Switch on AI features below to ask an AI, or try <tt>man " + esc(cmd.split()[0]) + "</tt> in a terminal."))
        for w in e.warnings:
            out.append(f"<span foreground='#ff9e64'><b>Careful:</b> {esc(w)}</span>")
        self.result.set_markup("\n\n".join(out))
        self.result.set_visible(True)

    def _explain_ai(self) -> None:
        cmd = self.cmd.get_text().strip()
        if not cmd:
            return
        s = dict(self.state.s)
        system, user = ai.explain_prompt(cmd, s["personality"])
        self.ai_explain_btn.set_sensitive(False)
        self.result.set_text("Thinking...")
        self.result.set_visible(True)

        def done(raw, err):
            self.ai_explain_btn.set_sensitive(True)
            self.result.set_text(str(err) if err else raw)

        run_async(lambda: ai.chat(s["provider"], s["model"], self.state.api_key, system, user, max_tokens=400), done)

    # ================================================================== test
    def _test(self) -> None:
        s = dict(self.state.s)
        self.test_btn.set_sensitive(False)
        self.status.set_text("Testing connection...")

        def done(raw, err):
            self.test_btn.set_sensitive(True)
            self.status.set_text(str(err) if err else f"Connection works. Sample: {content.clean_line(raw, 140)}")
            if not err and self.state.s["keyring_remember"] and self.state.api_key:
                ai.keyring_store(s["provider"], self.state.api_key)

        run_async(lambda: ai.chat(s["provider"], s["model"], self.state.api_key,
                                  "You are a friendly terminal companion. Reply in one short sentence.",
                                  "Greet me with a short, friendly Linux terminal welcome. No markdown.", max_tokens=80), done)

    def on_shown(self) -> None:
        super().on_shown()
        self.term.set_theme(self.win.current_theme(), animate=False)
        self._refresh()
        self._preview(roast=self.state.s["roast_mistakes"])

    def on_state(self, source: str) -> None:
        if source != "companion":
            self._loading = True
            s = self.state.s
            self.tips.set_active(s["tips_enabled"])
            self.faces.set_active(s["emotion_faces"])
            self.roast.set_active(s["roast_mistakes"])
            self.shortcuts.set_active(s["shell_shortcuts"])
            self._loading = False
            self._refresh()
