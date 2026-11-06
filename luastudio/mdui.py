import os

from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivymd.uix.button import MDButton, MDButtonText

from . import mdicons
from . import project as luaproject

BG = "#141218"
SURFACE = "#211F26"
SURFACE_3 = "#36343B"
SURFACE_PRESSED = "#3A3741"
PRIMARY = "#D0BCFF"
PRIMARY_PRESSED = "#B69DF8"
PRIMARY_CONTAINER = "#4F378B"
PRIMARY_CONTAINER_PRESSED = "#645093"
ON_PRIMARY = "#381E72"
ON_PRIMARY_CONTAINER = "#EADDFF"
TEXT = "#E6E1E5"
TEXT_DIM = "#CAC4D0"
TEXT_FAINT = "#938F99"
ERROR = "#F2B8B5"

STYLES = {
    "filled": (PRIMARY, ON_PRIMARY, PRIMARY_PRESSED),
    "tonal": (PRIMARY_CONTAINER, ON_PRIMARY_CONTAINER, PRIMARY_CONTAINER_PRESSED),
    "text": (None, PRIMARY, SURFACE_PRESSED),
}

GLYPH_CANDIDATES = [
    ["gamepad-variant", "gamepad", "controller"],
    ["rocket-launch", "rocket"],
    ["alien", "robot-happy"],
    ["dragon", "fire"],
    ["wizard-hat", "star-four-points"],
    ["puzzle", "shape"],
    ["orbit", "star-circle", "weather-night"],
    ["fire", "lightning-bolt"],
    ["cat", "paw"],
    ["frog", "paw"],
    ["bullseye-arrow", "target", "bullseye"],
    ["castle", "home"],
    ["robot", "robot-happy"],
    ["dice-multiple", "dice-5"],
    ["diamond-stone", "diamond"],
    ["mushroom", "sprout"],
    ["palette", "weather-sunny"],
    ["ghost", "emoticon-devil"],
    ["emoticon-cool", "paw"],
    ["car-sports", "car"],
    ["paw", "dinosaur"],
    ["penguin", "paw"],
    ["satellite-variant", "rocket"],
]

md_icon_exists = mdicons.exists


def _first_icon(names):
    for name in names:
        if md_icon_exists(name):
            return name
    return None


GLYPH_MD = {g: _first_icon(c) for g, c in zip(luaproject.ICON_GLYPHS, GLYPH_CANDIDATES)}


def rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0,
            int(h[4:6], 16) / 255.0, alpha)


def _initial_char(name):
    return next((ch.upper() for ch in (name or "") if ch.isalnum()), "?")


def lbl(text, size=14, color=TEXT, bold=False, halign="left", shorten=False, **kw):
    kw.setdefault("valign", "middle")
    if shorten:
        kw["shorten"] = True
        kw["shorten_from"] = "right" if halign == "left" else "left"
    lab = Label(text=text, font_size=sp(size), bold=bold, halign=halign,
                color=rgba(color), **kw)
    lab.bind(size=lambda w, v: setattr(w, "text_size", v))
    return lab


def wrap_label(text, size=13, color=TEXT_DIM, halign="left"):
    lab = Label(text=text, font_size=sp(size), halign=halign, valign="top",
                size_hint_y=None, color=rgba(color))
    lab.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    lab.bind(texture_size=lambda w, v: setattr(w, "height", v[1] + dp(4)))
    return lab


class Surface(BoxLayout):
    def __init__(self, bg=SURFACE, radius=28, **kw):
        BoxLayout.__init__(self, **kw)
        self._radius = dp(radius)
        with self.canvas.before:
            self._bg_col = Color(*rgba(bg))
            self._bg = RoundedRectangle(pos=self.pos, size=self.size,
                                        radius=[self._radius])
        self.bind(pos=self._sync_bg, size=self._sync_bg)

    def _sync_bg(self, *_a):
        self._bg.pos = self.pos
        self._bg.size = self.size


def surface_card(bg=SURFACE, radius=28, **kw):
    return Surface(bg=bg, radius=radius, **kw)


class FlatButton(ButtonBehavior, FloatLayout):
    def __init__(self, text="", icon=None, style="filled", **kw):
        self._bg, self._fg, self._pressed = STYLES.get(style, STYLES["filled"])
        super().__init__(**kw)
        with self.canvas.before:
            self._col = Color(*rgba(self._bg or SURFACE, 1.0 if self._bg else 0.0))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(20)])
        self._icon_w = mdicons.make_icon(icon, dp(20), rgba(self._fg)) if icon else None
        if self._icon_w is not None:
            self.add_widget(self._icon_w)
        self._label = Label(text=text, font_size=sp(14), bold=True,
                            color=rgba(self._fg), halign="left", valign="middle",
                            size_hint=(None, None), shorten=True,
                            shorten_from="right")
        self.label_widget = self._label
        self.add_widget(self._label)
        self.bind(pos=self._sync, size=self._sync, state=self._on_state)
        self._label.bind(texture_size=self._sync)
        self._sync()

    def _sync(self, *_a):
        self._rect.pos = self.pos
        self._rect.size = self.size
        has_icon = self._icon_w is not None
        has_text = bool(self._label.text)
        isz = dp(20)
        gap = dp(8) if (has_icon and has_text) else 0
        avail = max(self.width - dp(20), 0)
        text_avail = max(avail - ((isz + gap) if has_icon else 0), 0)
        cy = self.y + self.height / 2.0
        tw = th = 0
        if has_text:
            self._label.text_size = (text_avail, None)
            tw, th = self._label.texture_size
            self._label.size = (tw, th)
        group = ((isz if has_icon else 0) + gap + tw)
        x = self.x + (self.width - group) / 2.0
        if has_icon:
            self._icon_w.pos = (x, cy - isz / 2.0)
            x += isz + gap
        if has_text:
            self._label.pos = (x, cy - th / 2.0)

    def _on_state(self, _w, state):
        if state == "down":
            self._col.rgba = rgba(self._pressed, 1.0)
        else:
            self._col.rgba = rgba(self._bg or SURFACE, 1.0 if self._bg else 0.0)


def _run(cb):
    try:
        cb()
    except Exception:
        import traceback
        print(traceback.format_exc())


def md_button(text, cb, style="filled", icon=None, **kw):
    btn = FlatButton(text=text, icon=icon, style=style, **kw)
    btn.bind(on_release=lambda *_a: _run(cb))
    return btn


def icon_button(icon, **kw):
    kw.setdefault("style", "text")
    return FlatButton(text="", icon=icon, **kw)


def dialog_btn(text, cb, style="filled"):
    btn = MDButton(style=style)
    btn.add_widget(MDButtonText(text=text))
    btn.bind(on_release=lambda *_a: _run(cb))
    return btn


class IconTile(FloatLayout):
    def __init__(self, icon=None, name="", base_path=None, size_px=60,
                 image_abs=None, md_icon=None, **kw):
        kw.setdefault("size_hint", (None, None))
        kw["size"] = (size_px, size_px)
        super().__init__(**kw)
        self._px = size_px
        self._radius = size_px * 0.3
        self._md_override = md_icon
        self._initial = False
        self._content = None
        with self.canvas.before:
            self._fill = Color(*rgba(SURFACE_3))
            self._rect = RoundedRectangle(pos=self.pos, size=self.size,
                                          radius=[self._radius])
        self.bind(pos=self._sync, size=self._sync)
        self.set_icon(icon, name, base_path, image_abs)

    def _sync(self, *_a):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def set_color(self, hex_color):
        self._fill.rgba = rgba(hex_color)

    def set_name(self, name):
        if self._initial and self._content is not None:
            self._content.text = _initial_char(name)

    def set_icon(self, icon, name="", base_path=None, image_abs=None):
        icon = luaproject.normalize_icon(icon)
        self._fill.rgba = rgba(icon["color"])
        if self._content is not None:
            self.remove_widget(self._content)
            self._content = None
        self._initial = False
        path = image_abs
        if not path and icon.get("image") and base_path:
            path = os.path.join(base_path, icon["image"])
        if path and os.path.isfile(path):
            inner = self._px * 0.78
            self._content = Image(source=path, size_hint=(None, None),
                                  size=(inner, inner),
                                  pos_hint={"center_x": 0.5, "center_y": 0.5},
                                  fit_mode="contain")
        else:
            glyph = icon.get("glyph") or "@initial"
            md_name = self._md_override or GLYPH_MD.get(glyph)
            if md_name:
                self._content = mdicons.make_icon(md_name, self._px * 0.62,
                                                  (1, 1, 1, 0.96))
                if self._content is not None:
                    self._content.pos_hint = {"center_x": 0.5, "center_y": 0.5}
            if self._content is None:
                if glyph == "@initial":
                    self._initial = True
                    text = _initial_char(name)
                else:
                    text = glyph
                self._content = Label(text=text, bold=True, halign="center",
                                      valign="middle",
                                      font_size=self._px * 0.46,
                                      color=(1, 1, 1, 0.96),
                                      size_hint=(None, None),
                                      size=(self._px, self._px),
                                      pos_hint={"center_x": 0.5, "center_y": 0.5})
                self._content.bind(size=lambda w, v: setattr(w, "text_size", v))
        self.add_widget(self._content)


class PickTile(ButtonBehavior, IconTile):
    def __init__(self, **kw):
        super().__init__(**kw)
        with self.canvas.after:
            self._ring_col = Color(*rgba(PRIMARY, 0.0))
            self._ring = Line(rounded_rectangle=(0, 0, 1, 1, 1), width=dp(2))
        self.bind(pos=self._sync_ring, size=self._sync_ring)
        self._sync_ring()

    def _sync_ring(self, *_a):
        self._ring.rounded_rectangle = (self.x, self.y, self.width,
                                        self.height, self._radius)

    def set_selected(self, on):
        self._ring_col.a = 1.0 if on else 0.0


class Swatch(ButtonBehavior, FloatLayout):
    def __init__(self, color, size_px=None, **kw):
        size_px = size_px or dp(32)
        kw.setdefault("size_hint", (None, None))
        kw["size"] = (size_px, size_px)
        super().__init__(**kw)
        with self.canvas.before:
            Color(*rgba(color))
            self._dot = Ellipse(pos=self.pos, size=self.size)
        with self.canvas.after:
            self._ring_col = Color(*rgba(PRIMARY, 0.0))
            self._ring = Line(circle=(0, 0, 1), width=dp(2))
        self.bind(pos=self._sync, size=self._sync)
        self._sync()

    def _sync(self, *_a):
        self._dot.pos = self.pos
        self._dot.size = self.size
        r = self.width / 2.0
        self._ring.circle = (self.x + r, self.y + r, r + dp(3))

    def set_selected(self, on):
        self._ring_col.a = 1.0 if on else 0.0
