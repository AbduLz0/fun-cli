"""Animation toolkit.

GTK4 CSS has transitions but no @keyframes, so motion is driven with Adw animations.

`Motion` is a tiny container that draws its child at an offset *without* changing layout size,
so sliding a card in never shoves its neighbours around.

Everything respects (a) the desktop's "reduce animations" setting and (b) the app's own
"Reduce motion" switch: when off, widgets simply appear in their final state.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Graphene", "1.0")
gi.require_version("Gsk", "4.0")
from gi.repository import Adw, GLib, Graphene, Gsk, Gtk  # noqa: E402

_state = {"reduce": False}


def set_reduce_motion(value: bool) -> None:
    _state["reduce"] = bool(value)


def motion_ok(widget: Gtk.Widget | None = None) -> bool:
    if _state["reduce"]:
        return False
    settings = Gtk.Settings.get_default()
    return bool(settings.get_property("gtk-enable-animations")) if settings else True


class Motion(Gtk.Widget):
    """Draws `child` shifted by (dx, dy) and faded by opacity; never affects layout."""

    __gtype_name__ = "TesMotion"

    def __init__(self, child: Gtk.Widget | None = None):
        super().__init__()
        self._child: Gtk.Widget | None = None
        self.dx = 0.0
        self.dy = 0.0
        self._anims: list = []
        if child is not None:
            self.set_child(child)

    def set_child(self, child: Gtk.Widget | None) -> None:
        if self._child is not None:
            self._child.unparent()
        self._child = child
        if child is not None:
            child.set_parent(self)

    def get_child(self):
        return self._child

    def do_get_request_mode(self):
        # Without this GTK assumes a constant size and ignores the width, breaking wrapping labels/flowboxes.
        return self._child.get_request_mode() if self._child is not None else Gtk.SizeRequestMode.CONSTANT_SIZE

    def do_measure(self, orientation, for_size):
        if self._child is None:
            return 0, 0, -1, -1
        return self._child.measure(orientation, for_size)

    def do_size_allocate(self, width, height, baseline):
        if self._child is not None:
            t = Gsk.Transform().translate(Graphene.Point().init(self.dx, self.dy))
            self._child.allocate(width, height, baseline, t)

    def do_dispose(self):
        for a in self._anims:
            try:
                a.pause()
            except Exception:  # noqa: BLE001
                pass
        self._anims.clear()
        if self._child is not None:
            self._child.unparent()
            self._child = None
        Gtk.Widget.do_dispose(self)

    def offset(self, dx: float, dy: float) -> None:
        if dx != self.dx or dy != self.dy:
            self.dx, self.dy = dx, dy
            self.queue_allocate()

    # ------------------------------------------------------------ animations
    def _play(self, anim: Adw.Animation) -> Adw.Animation:
        self._anims = [a for a in self._anims if a.get_state() == Adw.AnimationState.PLAYING]
        self._anims.append(anim)
        anim.play()
        return anim

    def rise(self, delay_ms: int = 0, distance: float = 18.0, duration: int = 480) -> None:
        """Fade + slide up into place."""
        if not motion_ok(self):
            self.offset(0, 0)
            self.set_opacity(1.0)
            return
        self.set_opacity(0.0)
        self.offset(0, distance)

        def tick(v):
            self.set_opacity(min(1.0, v * 1.6))
            self.offset(0, distance * (1.0 - v))

        def start():
            anim = Adw.TimedAnimation.new(self, 0.0, 1.0, duration, Adw.CallbackAnimationTarget.new(tick))
            anim.set_easing(Adw.Easing.EASE_OUT_CUBIC)
            self._play(anim)
            return GLib.SOURCE_REMOVE

        if delay_ms > 0:
            GLib.timeout_add(delay_ms, start)
        else:
            start()

    def pop(self, height: float = 10.0, duration: int = 520) -> None:
        """A little hop with a bouncy landing - used when you pick something."""
        if not motion_ok(self):
            return
        anim = Adw.TimedAnimation.new(self, 1.0, 0.0, duration,
                                      Adw.CallbackAnimationTarget.new(lambda v: self.offset(self.dx, -height * v)))
        anim.set_easing(Adw.Easing.EASE_OUT_BOUNCE)
        self._play(anim)

    def bob(self, amplitude: float = 5.0, duration: int = 2200) -> None:
        """Endless gentle floating, like breathing."""
        if not motion_ok(self):
            return
        anim = Adw.TimedAnimation.new(self, -amplitude, amplitude, duration,
                                      Adw.CallbackAnimationTarget.new(lambda v: self.offset(self.dx, v)))
        anim.set_easing(Adw.Easing.EASE_IN_OUT_SINE)
        anim.set_repeat_count(0)
        anim.set_alternate(True)
        self._play(anim)


def stagger(items: list[Motion], step_ms: int = 70, start_ms: int = 0, **kw) -> None:
    for i, m in enumerate(items):
        m.rise(delay_ms=start_ms + i * step_ms, **kw)


def tween(widget: Gtk.Widget, frm: float, to: float, duration: int, callback, easing=Adw.Easing.EASE_OUT_CUBIC,
          done=None) -> Adw.TimedAnimation:
    """Run callback(value) from `frm` to `to`. Jumps straight to the end when motion is off."""
    if not motion_ok(widget):
        callback(to)
        if done:
            done()
        return None
    anim = Adw.TimedAnimation.new(widget, frm, to, duration, Adw.CallbackAnimationTarget.new(callback))
    anim.set_easing(easing)
    if done:
        anim.connect("done", lambda *_: done())
    anim.play()
    return anim


def flash_class(widget: Gtk.Widget, css_class: str, ms: int = 900) -> None:
    """Add a CSS class briefly - CSS transitions turn that into a smooth glow/pulse."""
    widget.add_css_class(css_class)
    GLib.timeout_add(ms, lambda: (widget.remove_css_class(css_class), GLib.SOURCE_REMOVE)[1])
