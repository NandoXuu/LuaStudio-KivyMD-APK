# -*- coding: utf-8 -*-
"""Design system da IDE: Material 3 Expressive (estilo Jetpack Compose M3 /
Flutter), so para a interface do editor (nao afeta o app gerado pelo Lua).

Ideias do M3 Expressive usadas aqui:
  * paleta tonal roxa (superficie -> container -> container alto), com UMA
    cor de destaque (primary container) e texto em "on-surface";
  * escala de formas: None 0 / XS 4 / S 8 / M 12 / L 16 / XL 28 / Full;
  * botoes em PILULA que fazem *shape morphing* (ficam menos redondos ao
    toque) + state layer suave;
  * grupos de botoes conectados (cantos internos pequenos, o selecionado
    vira pilula), navigation rail com indicador pill, cards grandes (28);
  * dialogos de cantos extra-grandes e campos de texto arredondados.
Tambem tem os helpers de animacao leve (fade, botao, popup)."""

import os
import struct
import tempfile
import zlib

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.properties import BooleanProperty, ListProperty, NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.metrics import dp

from . import mdicons
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.utils import get_color_from_hex

from . import softkeyboard

# ---------------------------------------------------- escala de formas M3
SHAPE_NONE = 0
SHAPE_XS = 4
SHAPE_S = 8
SHAPE_M = 12
SHAPE_L = 16
SHAPE_XL = 28
SHAPE_FULL = 999

# ---------------------------------------------------------------- paleta
# (tons de superficie do M3 escuro, semente roxa)
BG = (0.078, 0.071, 0.094, 1)          # surface (fundo da janela)
SURFACE = (0.141, 0.125, 0.169, 1)     # surface container (cards/paineis)
SURFACE_2 = (0.188, 0.169, 0.224, 1)   # container alto (botoes tonais)
SURFACE_HOVER = (0.239, 0.220, 0.278, 1)  # container mais alto / pressionado
BORDER = (0.298, 0.278, 0.337, 1)      # outline variant

TEXT = (0.902, 0.878, 0.914, 1)        # on-surface
TEXT_DIM = (0.792, 0.769, 0.816, 1)    # on-surface-variant
TEXT_FAINT = (0.576, 0.557, 0.608, 1)  # detalhes terciarios (caminhos, datas)

ACCENT = (0.380, 0.310, 0.570, 1)      # primary container (acao principal)
ACCENT_LIGHT = (0.816, 0.737, 1.000, 1)  # primary (icones/realces)
ON_ACCENT = (0.918, 0.867, 1.000, 1)   # on-primary-container
SECONDARY = (0.290, 0.267, 0.349, 1)   # secondary container (indicador do rail)
ON_SECONDARY = (0.910, 0.870, 0.973, 1)
PLAY = (0.231, 0.482, 0.357, 1)        # verde tonal (Play)
STOP = (0.690, 0.294, 0.341, 1)        # vermelho tonal (Stop / apagar)
WARN = (0.878, 0.714, 0.412, 1)        # ambar (avisos)

EDITOR_BG = (0.110, 0.098, 0.133, 1)
CONSOLE_BG = (0.094, 0.082, 0.114, 1)
INPUT_BG = (0.188, 0.169, 0.224, 1)
CURSOR = (0.816, 0.737, 1.000, 1)
OVERLAY = (0, 0, 0, 0.62)              # scrim atras dos dialogos

MONO_BG = (0.141, 0.125, 0.169, 1)     # fundo do editor (= card, sem 'caixa' dentro do card)
MONO_BG_DARK = (0.110, 0.098, 0.133, 1)
MONO_FG = (0.80, 0.82, 0.98, 1)
MONO_DIM = (0.36, 0.34, 0.42, 1)
MONO_SEL = (0.30, 0.26, 0.42, 1)
MONO_BTN = (0.188, 0.169, 0.224, 1)

INDENT_COLORS = [
    (1.000, 0.560, 0.760),  # rosa pastel vivo
    (0.420, 0.900, 1.000),  # ciano pastel
    (0.760, 0.680, 1.000),  # lilas pastel
    (0.500, 1.000, 0.720),  # verde menta
    (1.000, 0.850, 0.480),  # amarelo pastel
    (0.820, 0.560, 1.000),  # violeta
    (1.000, 0.680, 0.430),  # pêssego
    (0.520, 0.800, 1.000),  # azul pastel
]


def _build_tolerant(cls, optional, **kw):
    """Cria `cls(**kw)`; se essa versao do Kivy nao conhecer alguma
    propriedade OPCIONAL (so enfeite visual), tenta de novo sem ela em vez
    de derrubar o app."""
    kw = dict(kw)
    while True:
        try:
            return cls(**kw)
        except TypeError:
            dropped = False
            for key in optional:
                if key in kw:
                    kw.pop(key)
                    dropped = True
                    break
            if not dropped:
                raise


def hex_to_rgba(value, default=SURFACE_2):
    """'#RRGGBB' -> (r, g, b, a) do Kivy. Devolve `default` se invalido."""
    try:
        return tuple(get_color_from_hex(value))
    except Exception:
        return default


# ------------------------------------------------------------ animacoes
def fade_in(widget, delay=0.0, duration=0.22):
    """Fade-in leve de um widget (opcionalmente atrasado, pra escalonar
    varios itens - efeito 'cascata')."""
    widget.opacity = 0
    anim = Animation(opacity=1, d=duration, t="out_quad")
    if delay > 0:
        Clock.schedule_once(lambda *_a: anim.start(widget), delay)
    else:
        anim.start(widget)


# ------------------------------------------- retangulo arredondado (PNG)
_RR_CACHE = {}


def rounded_png(radius=28, aa=1.0):
    """Gera (uma vez) um PNG branco de retangulo arredondado, pronto pra
    virar 9-patch (BorderImage). Usado como fundo dos dialogos, porque o
    Popup do Kivy so desenha fundo por imagem. PNG escrito na mao (sem
    Pillow). Devolve o caminho do arquivo ou '' se nao deu pra gravar."""
    radius = int(radius)
    if radius in _RR_CACHE:
        return _RR_CACHE[radius]
    path = ""
    try:
        size = radius * 2 + 2
        rows = []
        for y in range(size):
            row = bytearray([0])
            for x in range(size):
                px, py = x + 0.5, y + 0.5
                cx = min(max(px, radius), size - radius)
                cy = min(max(py, radius), size - radius)
                dist = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
                a = max(0.0, min(1.0, (radius - dist) / aa + 0.5))
                row += bytes((255, 255, 255, int(a * 255)))
            rows.append(bytes(row))
        raw = b"".join(rows)

        def chunk(tag, data):
            c = struct.pack(">I", len(data)) + tag + data
            return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)

        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw, 9))
               + chunk(b"IEND", b""))
        path = os.path.join(tempfile.gettempdir(), "luastudio_m3_rr%d.png" % radius)
        with open(path, "wb") as fh:
            fh.write(png)
    except Exception:
        path = ""
    _RR_CACHE[radius] = path
    return path


def styled_popup(title, content, size_hint=(0.9, 0.8), **kw):
    """Dialogo M3: cantos extra-grandes (28), fundo em container alto,
    titulo alinhado a esquerda, sem separador, scrim atras e fade-in."""
    path = rounded_png(SHAPE_XL)
    kw.setdefault("title_color", TEXT)
    kw.setdefault("title_size", 20)
    kw.setdefault("title_align", "left")
    kw.setdefault("separator_height", 0)
    kw.setdefault("overlay_color", OVERLAY)
    if path:
        kw.setdefault("background", path)
        kw.setdefault("border", [SHAPE_XL] * 4)
        kw.setdefault("background_color", SURFACE)
    else:
        kw.setdefault("background", "")
        kw.setdefault("background_color", SURFACE)
    popup = _build_tolerant(
        Popup, ("title_align", "overlay_color", "separator_height", "border",
                "background"),
        title=title, content=content, size_hint=size_hint, **kw)
    popup.opacity = 0
    popup.bind(on_pre_open=lambda *_a: Animation(
        opacity=1, d=0.18, t="out_quad").start(popup))
    return popup


def make_input(**kw):
    """Campo de texto M3 (filled, cantos 16): fundo tonal arredondado e
    contorno que acende na cor primaria quando recebe foco."""
    kw.setdefault("multiline", False)
    kw.setdefault("background_normal", "")
    kw.setdefault("background_active", "")
    kw.setdefault("background_disabled_normal", "")
    kw.setdefault("background_color", (0, 0, 0, 0))
    kw.setdefault("foreground_color", TEXT)
    kw.setdefault("hint_text_color", TEXT_DIM[:3] + (0.7,))
    kw.setdefault("cursor_color", CURSOR)
    kw.setdefault("selection_color", ACCENT_LIGHT[:3] + (0.30,))
    kw.setdefault("padding", (16, 15, 16, 15))
    kw.setdefault("font_size", 16)
    ti = _build_tolerant(TextInput, ("hint_text_color", "background_disabled_normal",
                                     "selection_color"), **kw)
    try:
        border_c = Color(*BORDER[:3], 0.0)
        border_r = RoundedRectangle(pos=ti.pos, size=ti.size, radius=[SHAPE_L])
        fill_c = Color(*INPUT_BG)
        fill_r = RoundedRectangle(pos=ti.pos, size=ti.size, radius=[SHAPE_L])
        cb = ti.canvas.before
        # inseridos NO INICIO: as instrucoes do proprio TextInput (cursor,
        # cor do texto) continuam vindo depois, sem herdar a nossa cor.
        for i, ins in enumerate((border_c, border_r, fill_c, fill_r)):
            cb.insert(i, ins)

        def _sync(*_a):
            x, y = ti.pos
            w, h = ti.size
            border_r.pos, border_r.size = (x, y), (w, h)
            fill_r.pos = (x + 2, y + 2)
            fill_r.size = (max(w - 4, 0), max(h - 4, 0))
            fill_r.radius = [max(SHAPE_L - 2, 0)]

        def _focus(_w, on):
            Animation(rgba=(ACCENT_LIGHT if on else BORDER[:3] + (0.0,)),
                      d=0.14).start(border_c)

        ti.bind(pos=_sync, size=_sync, focus=_focus)
        _sync()
    except Exception:
        ti.background_color = INPUT_BG
    softkeyboard.bind_textinput(ti)
    return ti


def paint_rounded(widget, color=SURFACE, radius=SHAPE_XL, border=None, border_w=1):
    """Desenha um fundo arredondado (com borda fina opcional) atras de
    `widget`. Devolve a instrucao Color do preenchimento (pra trocar a cor
    depois, se precisar)."""
    with widget.canvas.before:
        if border:
            Color(*border)
            brect = RoundedRectangle(pos=widget.pos, size=widget.size,
                                     radius=[radius])
        else:
            brect = None
        fill = Color(*color)
        rect = RoundedRectangle(pos=widget.pos, size=widget.size,
                                radius=[radius])

    def _sync(*_a):
        x, y = widget.pos
        w, h = widget.size
        if brect is not None:
            brect.pos = (x, y)
            brect.size = (w, h)
            rect.pos = (x + border_w, y + border_w)
            rect.size = (max(w - 2 * border_w, 0), max(h - 2 * border_w, 0))
        else:
            rect.pos = (x, y)
            rect.size = (w, h)

    widget.bind(pos=_sync, size=_sync)
    _sync()
    return fill


# ------------------------------------------------------------- botoes
class RoundButton(Button):
    """Botao M3 Expressive: PILULA em repouso e *shape morphing* ao tocar
    (os cantos ficam menos redondos enquanto pressionado), com state layer
    suave por cima da cor.

    `pill=True` (padrao) ignora `radius` e usa a pilula (limitada a 28 em
    botoes altos). `pill=False` usa `radius`. `corners=[tl,tr,br,bl]` fixa
    os cantos (usado pelos grupos conectados)."""

    bg_color = ListProperty(list(SURFACE_2))
    radius = NumericProperty(SHAPE_M)
    pill = BooleanProperty(True)
    corners = ListProperty([])
    press_t = NumericProperty(0.0)   # 0 = solto, 1 = pressionado (animado)

    def __init__(self, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_down", "")
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("color", TEXT)
        Button.__init__(self, **kw)
        with self.canvas.before:
            self._c = Color(*self._current_rgba())
            self._rect = RoundedRectangle(pos=self.pos, size=self.size,
                                          radius=self._radii())
        self.bind(pos=self._sync_geom, size=self._sync_geom,
                  radius=self._sync_geom, pill=self._sync_geom,
                  corners=self._sync_geom, press_t=self._sync_all,
                  bg_color=self._sync_color, disabled=self._sync_color,
                  state=self._on_state)

    def _radii(self):
        if self.corners and len(self.corners) == 4:
            return list(self.corners)
        w, h = self.size
        half = max(min(h, w) / 2.0, 0.0)
        if self.pill:
            rest = min(half, SHAPE_XL)
        else:
            rest = min(float(self.radius), half)
        # morph: ao tocar, vira um "squircle" (menos redondo)
        press = min(rest, max(10.0, h * 0.30))
        r = rest + (press - rest) * self.press_t
        return [r, r, r, r]

    def _current_rgba(self):
        r, g, b, a = self.bg_color
        t = self.press_t
        if (r + g + b) < 1.2:
            # superficie escura: o state layer CLAREIA
            mix = 0.14 * t
            r, g, b = r + (1 - r) * mix, g + (1 - g) * mix, b + (1 - b) * mix
        else:
            k = 1.0 - 0.14 * t
            r, g, b = r * k, g * k, b * k
        if a < 0.5:
            a = max(a, 0.16 * t)      # botao transparente: so o state layer
        if self.disabled:
            a = a * 0.45
        return (r, g, b, a)

    def _sync_geom(self, *_a):
        self._rect.pos = self.pos
        self._rect.size = self.size
        self._rect.radius = self._radii()

    def _sync_color(self, *_a):
        self._c.rgba = self._current_rgba()

    def _sync_all(self, *_a):
        self._sync_color()
        self._sync_geom()

    def _on_state(self, _w, value):
        down = (value == "down")
        Animation.cancel_all(self, "press_t")
        Animation(press_t=1.0 if down else 0.0,
                  d=0.10 if down else 0.28,
                  t="out_quad" if down else "out_back").start(self)




def _measure(text, font_size, font_name=None, bold=False):
    """Largura natural do texto (px), medida fora do widget."""
    if not text:
        return 0
    try:
        from kivy.core.text import Label as CoreLabel
        kw = dict(text=text, font_size=font_size, bold=bold)
        if font_name:
            kw["font_name"] = font_name
        cl = CoreLabel(**kw)
        cl.refresh()
        return cl.texture.size[0]
    except Exception:
        return len(text) * font_size * 0.56


class IconButton(RoundButton):
    """RoundButton com icone PNG real (tingido com a cor do texto). Com
    texto, o conjunto icone+rotulo fica centralizado, como no M3."""
    def __init__(self, icon=None, icon_size=22, icon_left=True, **kw):
        self.icon_name = icon
        self.icon_size = dp(icon_size)
        self.icon_left = icon_left
        super().__init__(**kw)
        self._icon_img = None
        if icon:
            md_name = mdicons.resolve(icon)
            if md_name:
                self._icon_img = mdicons.make_icon(md_name, self.icon_size, self.color)
            if self._icon_img is not None:
                self._icon_img.color = self.color
                self.add_widget(self._icon_img)
                self.bind(pos=self._sync_icon, size=self._sync_icon,
                          text=self._sync_icon, color=self._tint_icon)
                Clock.schedule_once(lambda *_: self._sync_icon(), 0)

    def _tint_icon(self, *_a):
        if self._icon_img is not None:
            self._icon_img.color = self.color

    def _sync_icon(self, *_):
        if not self._icon_img:
            return
        iy = self.y + (self.height - self.icon_size) / 2
        if not self.text:
            self._icon_img.pos = (self.x + (self.width - self.icon_size) / 2, iy)
            return
        gap = dp(8)
        tw = _measure(self.text, self.font_size, self.font_name, self.bold)
        group = self.icon_size + gap + tw
        avail = max(self.width - dp(24), 0)
        if group > avail:                       # nao cabe: icone na ponta
            start = self.x + dp(12)
            shift = 0
        else:
            start = self.x + (self.width - group) / 2
            shift = (self.icon_size + gap)
        self._icon_img.pos = (start, iy)
        self.text_size = (max(self.width - dp(8), 0), self.height)
        self.halign = "center"
        self.valign = "middle"
        try:
            # texto deslocado pro lado do icone (conjunto centralizado)
            self.padding = (shift if group <= avail else self.icon_size + dp(20),
                            0, 0, 0)
        except Exception:
            self.padding = (self.icon_size + dp(14), 0)


# --------------------------------------------------- superficies / cards
class Card(BoxLayout):
    """Container M3: fundo tonal arredondado (28 por padrao), sem borda
    dura. Use `bg_color` / `radius` pra variar."""

    bg_color = ListProperty(list(SURFACE))
    radius = NumericProperty(SHAPE_XL)

    def __init__(self, **kw):
        kw.setdefault("orientation", "vertical")
        BoxLayout.__init__(self, **kw)
        with self.canvas.before:
            self._c = Color(*self.bg_color)
            self._r = RoundedRectangle(pos=self.pos, size=self.size,
                                       radius=[self.radius])
        self.bind(pos=self._sync, size=self._sync, radius=self._sync,
                  bg_color=self._sync)

    def _sync(self, *_a):
        self._c.rgba = self.bg_color
        self._r.pos = self.pos
        self._r.size = self.size
        self._r.radius = [min(self.radius, self.height / 2.0,
                              self.width / 2.0)]


class ConnectedGroup(BoxLayout):
    """Grupo de botoes CONECTADOS (M3 Expressive): cantos internos
    pequenos, cantos externos totalmente redondos; o item selecionado
    vira uma pilula completa na cor de destaque.

    options: lista de valores; labels: {valor: texto}; on_pick(valor)."""

    def __init__(self, options, current=None, on_pick=None, labels=None,
                 height=44, font_size=13, **kw):
        kw.setdefault("size_hint_y", None)
        kw["height"] = height
        kw.setdefault("spacing", 2)
        BoxLayout.__init__(self, **kw)
        self.options = list(options)
        self.current = current
        self.on_pick = on_pick
        self.btns = {}
        for opt in self.options:
            text = (labels or {}).get(opt, str(opt))
            b = RoundButton(text=text, font_size=font_size, pill=False,
                            bg_color=SURFACE_2)
            b.bind(on_release=lambda _b, v=opt: self.select(v, True))
            self.btns[opt] = b
            self.add_widget(b)
        self._restyle()

    def _restyle(self):
        full = self.height / 2.0
        small = SHAPE_S
        n = len(self.options)
        for i, opt in enumerate(self.options):
            b = self.btns[opt]
            if opt == self.current:
                b.corners = [full, full, full, full]
                b.bg_color = list(ACCENT)
                b.color = ON_ACCENT
            else:
                left = full if i == 0 else small
                right = full if i == n - 1 else small
                b.corners = [left, right, right, left]
                b.bg_color = list(SURFACE_2)
                b.color = TEXT

    def select(self, value, notify=False):
        self.current = value
        self._restyle()
        if notify and self.on_pick:
            self.on_pick(value)


class NavRail(Card):
    """Navigation rail M3: coluna estreita dentro de um card arredondado.
    O item ativo ganha um indicador PILL; o rotulo fica logo abaixo.

    items: [(chave, nome_do_icone_png, rotulo)]; on_select(chave)."""

    def __init__(self, items, on_select, width=76, **kw):
        kw.setdefault("size_hint_x", None)
        kw["width"] = width
        kw.setdefault("padding", (8, 12, 8, 10))
        kw.setdefault("spacing", 6)
        kw.setdefault("radius", SHAPE_XL)
        Card.__init__(self, **kw)
        self.on_select = on_select
        self._items = {}
        self.active = None
        for key, icon, label in items:
            col = BoxLayout(orientation="vertical", size_hint_y=None,
                            height=62, spacing=2)
            ind = IconButton(icon=icon, text="", bg_color=[0, 0, 0, 0],
                             size_hint=(None, None), size=(52, 32),
                             pos_hint={"center_x": 0.5})
            ind.bind(on_release=lambda _b, k=key: self._tap(k))
            holder = BoxLayout(size_hint_y=None, height=32)
            holder.add_widget(Widget_spacer())
            holder.add_widget(ind)
            holder.add_widget(Widget_spacer())
            lab = Label(text=label, font_size=11, color=TEXT_DIM,
                        size_hint_y=None, height=16)
            col.add_widget(holder)
            col.add_widget(lab)
            self._items[key] = (ind, lab)
            self.add_widget(col)
        self.add_widget(Widget_spacer())

    def _tap(self, key):
        self.set_active(key)
        try:
            self.on_select(key)
        except Exception:
            import traceback
            traceback.print_exc()

    def set_active(self, key):
        self.active = key
        for k, (ind, lab) in self._items.items():
            on = (k == key)
            Animation(bg_color=list(SECONDARY if on else (0, 0, 0, 0)),
                      d=0.18, t="out_quad").start(ind)
            lab.color = TEXT if on else TEXT_DIM
            lab.bold = on


def Widget_spacer():
    from kivy.uix.widget import Widget
    return Widget()


class Panel(object):
    """Mixin simples: desenha um fundo solido atras de um layout (pra
    diferenciar toolbar/barra de simbolos do resto da tela)."""

    def paint_panel(self, widget, color=SURFACE):
        with widget.canvas.before:
            Color(*color)
            rect = Rectangle(pos=widget.pos, size=widget.size)
        widget.bind(pos=lambda *a: setattr(rect, "pos", widget.pos),
                   size=lambda *a: setattr(rect, "size", widget.size))
        return rect


# Temas selecionaveis e cor de destaque configuravel pela IDE.
THEMES = {
    "dark": {"BG": (0.078, 0.071, 0.094, 1), "SURFACE": (0.141, 0.125, 0.169, 1), "TEXT": (0.902, 0.878, 0.914, 1)},
    "oled": {"BG": (0, 0, 0, 1), "SURFACE": (0.071, 0.063, 0.086, 1), "TEXT": (0.94, 0.94, 0.96, 1)},
    "light": {"BG": (0.996, 0.969, 1.0, 1), "SURFACE": (0.953, 0.929, 0.969, 1), "TEXT": (0.114, 0.106, 0.125, 1)},
    "high-contrast": {"BG": (0, 0, 0, 1), "SURFACE": (0.04, 0.04, 0.04, 1), "TEXT": (1, 1, 1, 1)},
}


def apply_preferences(theme_name=None, accent_color=None):
    """Atualiza a paleta global; widgets existentes podem precisar ser redesenhados."""
    global BG, SURFACE, TEXT, ACCENT
    if theme_name:
        palette = THEMES.get(str(theme_name).lower())
        if palette:
            BG, SURFACE, TEXT = palette["BG"], palette["SURFACE"], palette["TEXT"]
    if accent_color:
        c = hex_to_rgba(accent_color, ACCENT)
        if len(c) == 4:
            ACCENT = c
    return {"BG": BG, "SURFACE": SURFACE, "TEXT": TEXT, "ACCENT": ACCENT}
