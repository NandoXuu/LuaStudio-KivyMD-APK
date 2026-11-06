"""Seletores visuais: o usuário final escolhe a área ou o elemento na tela."""
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle
from kivy.uix.widget import Widget

from .region import Region


class _Overlay(Widget):
    def __init__(self, **kw):
        super().__init__(size_hint=(None, None), pos=(0, 0), size=Window.size, **kw)
        Window.bind(size=self._fit)
        Window.bind(on_key_down=self._key)
        self.cancel_cb = None

    def _fit(self, w, size):
        self.size = size

    def _key(self, win, key, *a):
        if key == 27:                       # ESC cancela
            self.close(cancelled=True)
            return True

    def open(self):
        Window.add_widget(self)             # fica por cima de tudo

    def close(self, cancelled=False):
        Window.unbind(size=self._fit)
        Window.unbind(on_key_down=self._key)
        if self.parent:
            self.parent.remove_widget(self)   # sai da tela ANTES de capturar
        if cancelled and self.cancel_cb:
            self.cancel_cb()


class _AreaOverlay(_Overlay):
    def __init__(self, on_done, min_size=8, **kw):
        super().__init__(**kw)
        self.on_done, self.min_size = on_done, min_size
        self.a = self.b = None
        self._draw()

    def _draw(self):
        self.canvas.clear()
        with self.canvas:
            Color(0, 0, 0, 0.35)
            Rectangle(pos=self.pos, size=self.size)
            if self.a and self.b:
                x, y = min(self.a[0], self.b[0]), min(self.a[1], self.b[1])
                w, h = abs(self.a[0] - self.b[0]), abs(self.a[1] - self.b[1])
                Color(1, 1, 1, 0.15)
                Rectangle(pos=(x, y), size=(w, h))
                Color(0.2, 0.8, 1, 1)
                Line(rectangle=(x, y, w, h), width=1.5)

    def on_touch_down(self, t):
        self.a = self.b = t.pos; self._draw(); return True

    def on_touch_move(self, t):
        self.b = t.pos; self._draw(); return True

    def on_touch_up(self, t):
        self.b = t.pos
        x, y = min(self.a[0], self.b[0]), min(self.a[1], self.b[1])
        w, h = abs(self.a[0] - self.b[0]), abs(self.a[1] - self.b[1])
        self.close()
        if w >= self.min_size and h >= self.min_size:
            # coordenadas de toque do Kivy = origem embaixo-esquerda
            self.on_done(Region(x, y, w, h, unit="px", origin="bottom-left"))
        elif self.cancel_cb:
            self.cancel_cb()
        return True


class _PickOverlay(_Overlay):
    def __init__(self, on_done, root=None, **kw):
        super().__init__(**kw)
        self.on_done, self.root = on_done, root
        with self.canvas:
            Color(0.2, 0.8, 1, 0.12)
            Rectangle(pos=self.pos, size=self.size)

    def _find(self, pos):
        root = self.root or Window
        best, best_area = None, None
        for w in root.walk(restrict=True):
            if w is self or w is root or w is Window:
                continue
            if getattr(w, "opacity", 1) <= 0 or w.width <= 0 or w.height <= 0:
                continue
            try:
                inside = w.collide_point(*w.to_widget(*pos))
            except Exception:
                continue
            if inside:
                area = w.width * w.height
                if best is None or area <= best_area:   # o menor que contém o toque
                    best, best_area = w, area
        return best

    def on_touch_down(self, t):
        self.close()                         # tira o overlay antes de procurar
        w = self._find(t.pos)
        if w is not None:
            self.on_done(w)
        elif self.cancel_cb:
            self.cancel_cb()
        return True


def select_region(on_done, on_cancel=None, min_size=8):
    """Usuário arrasta um retângulo; on_done(Region). ESC cancela."""
    ov = _AreaOverlay(on_done, min_size)
    ov.cancel_cb = on_cancel
    ov.open()
    return ov


def pick_widget(on_done, on_cancel=None, root=None):
    """Usuário toca num elemento; on_done(widget). ESC cancela."""
    ov = _PickOverlay(on_done, root)
    ov.cancel_cb = on_cancel
    ov.open()
    return ov
