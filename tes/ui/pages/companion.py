"""AI Companion: greeting pack, command explainer, provider setup. Works offline; AI is an optional upgrade."""
from __future__ import annotations

import webbrowser

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ...core import ai, bashconfig, content, explain
from ..common import Page, combo_row, group, label, run_async
from ..widgets import TerminalPreview

PROVIDER_NAMES = list(ai.PROVIDERS)


class CompanionPage(Page):
    page_id = "companion"
    title = "AI Companion"
    subtitle = "Give your terminal a personality. Everything here works offline - AI is an optional extra."
    icon = "tes-companion-symbolic"

    def __init__(self, win):
        super().__init__(win)
        s = self.state.s
        self._loading = True
        self.term = TerminalPreview("companion", max_height=170, min_height=110)
        self.pin(self.term)
        self.header("Companion")

        # ---- personality + greeting pack
        pg = group("Personality &amp; greetings",
                   "Your terminal shows one line from this list each time it opens. They're saved in a plain file, "
                   "so opening a terminal never waits on the internet.")
        self.name_row = Adw.EntryRow(title="Companion name")
        self.name_row.set_text(s["name"])
        self.name_row.connect("changed", lambda r: self._opt(name=r.get_text()[:40] or "Terminal friend"))
        pg.add(self.name_row)
        self.persona = combo_row("Personality", list(content.PERSONALITIES), list(content.PERSONALITIES).index(s["personality"]) if s["personality"] in content.PERSONALITIES else 0)
        self.persona.connect("notify::selected", lambda r, _p: self._opt(personality=list(content.PERSONALITIES)[r.get_selected()]))
        pg.add(self.persona)
        r = Adw.ActionRow(title="Greeting list", subtitle="")
        self.pack_sub = r
        self.builtin_btn = Gtk.Button(label="Use built-in tips", valign=Gtk.Align.CENTER)
        self.gen_btn = Gtk.Button(label="Write with AI", valign=Gtk.Align.CENTER)
        self.gen_btn.add_css_class("suggested-action")
        self.builtin_btn.connect("clicked", lambda _b: self._use_builtin())
        self.gen_btn.connect("clicked", lambda _b: self._generate())
        r.add_suffix(self.builtin_btn)
        r.add_suffix(self.gen_btn)
        pg.add(r)
        self.add(pg)
        self.pack_view = Gtk.Label(xalign=0, wrap=True, selectable=False)
        self.pack_view.add_css_class("tes-result")
        self.pack_view.add_css_class("tes-code")
        self.add(self.pack_view)

        # ---- explainer
        eg = group("What does this command do?", "Paste any command. Common ones are explained instantly and offline; risky ones get a clear warning.")
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

        # ---- provider
        ag = group("AI provider (optional)", "Skip this and the app works exactly the same, just without AI writing.")
        self.enable = Adw.SwitchRow(title="Enable AI features", subtitle="AI is only ever called when you press a button.", active=s["ai_enabled"])
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
        self.remember = Adw.SwitchRow(title="Remember key in my desktop keyring", active=s["keyring_remember"])
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
        self.add(label("Privacy: your key is never written to settings or your shell files. It stays in memory, or in your desktop keyring if you switch that on.", "tes-note"))

        self._loading = False
        self._refresh()

    # ------------------------------------------------------------------ helpers
    def _info(self) -> dict:
        return ai.PROVIDERS[PROVIDER_NAMES[self.provider.get_selected()]]

    def _opt(self, **kw) -> None:
        if self._loading:
            return
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
        if not self._loading:
            self.state.api_key = row.get_text().strip()

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

    def _refresh(self) -> None:
        s = self.state.s
        needs_key = ai.PROVIDERS[PROVIDER_NAMES[self.provider.get_selected()]]["needs_key"]
        self.key.set_visible(needs_key)
        self.remember.set_visible(needs_key)
        usable = bool(s["ai_enabled"])
        self.gen_btn.set_sensitive(usable)
        self.ai_explain_btn.set_sensitive(usable)
        self.test_btn.set_sensitive(usable)
        self.gen_btn.set_tooltip_text(None if usable else "Switch on AI features below first.")
        pack = bashconfig.read_greetings()
        self.pack_sub.set_subtitle(f"{len(pack)} lines saved" if pack else "Nothing saved yet - using the built-in tips")
        self.pack_view.set_text("\n".join("  " + l for l in (pack or content.OFFLINE_GREETINGS)[:14]))
        self.term.set_accent(s["accent"])

    def _lines_preview(self) -> None:
        pack = bashconfig.read_greetings() or content.OFFLINE_GREETINGS
        self.term.set_lines([[(f"{self.state.s['face']}  ", "accent"), (f"{self.state.s['name']} says:", "fg")],
                             [(pack[0], "dim")], [(pack[len(pack) // 2], "dim")]], animate=True)

    # ------------------------------------------------------------------ greeting pack
    def _use_builtin(self) -> None:
        bashconfig.write_greetings(content.OFFLINE_GREETINGS)
        self.state.update("companion", greeting_pack=True)
        self._refresh()
        self._lines_preview()
        self.win.toast("Built-in tips saved. Apply to Bash to use them.")

    def _generate(self) -> None:
        s = self.state.s
        system, user = ai.greeting_pack_prompt(s["name"], s["personality"])
        self.gen_btn.set_sensitive(False)
        self.status.set_text("Asking your companion to write greetings...")
        run_async(lambda: ai.chat(s["provider"], s["model"], self.state.api_key, system, user, max_tokens=500, temperature=0.9),
                  self._generated)

    def _generated(self, raw, err) -> None:
        self._refresh()
        if err:
            self.status.set_text(str(err))
            return
        lines = ai.parse_pack(raw)
        if len(lines) < 3:
            self.status.set_text("The AI's answer wasn't usable. Try again or use the built-in tips.")
            return
        bashconfig.write_greetings(lines)
        self.state.update("companion", greeting_pack=True)
        self.status.set_text(f"Saved {len(lines)} new greetings. Apply to Bash to use them.")
        self._refresh()
        self._lines_preview()

    # ------------------------------------------------------------------ explain
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
        s = self.state.s
        system, user = ai.explain_prompt(cmd, s["personality"])
        self.ai_explain_btn.set_sensitive(False)
        self.result.set_text("Thinking...")
        self.result.set_visible(True)

        def done(raw, err):
            self.ai_explain_btn.set_sensitive(True)
            self.result.set_text(str(err) if err else raw)

        run_async(lambda: ai.chat(s["provider"], s["model"], self.state.api_key, system, user, max_tokens=400), done)

    # ------------------------------------------------------------------ test
    def _test(self) -> None:
        s = self.state.s
        self.test_btn.set_sensitive(False)
        self.status.set_text("Testing connection...")

        def done(raw, err):
            self.test_btn.set_sensitive(True)
            self.status.set_text(str(err) if err else f"Connection works. Sample: {content.clean_line(raw, 140)}")
            if not err and self.state.s["keyring_remember"] and self.state.api_key:
                ai.keyring_store(s["provider"], self.state.api_key)

        run_async(lambda: ai.chat(s["provider"], s["model"], self.state.api_key,
                                  "You are a friendly terminal companion. Reply in one short sentence.",
                                  "Greet me with a short, friendly Linux terminal welcome. No markdown.", max_tokens=60), done)

    def on_shown(self) -> None:
        super().on_shown()
        self.term.set_theme(self.win.current_theme(), animate=False)
        self._refresh()
        self._lines_preview()

    def on_state(self, source: str) -> None:
        if source != "companion":
            self._refresh()
