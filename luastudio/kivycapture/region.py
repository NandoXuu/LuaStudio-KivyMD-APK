"""Alvos de captura: tela toda, área livre (x, y, largura, altura) ou widget.
Python puro (sem Kivy) para poder ser testado em qualquer lugar."""


RESOLUTIONS = {"SD": 480, "HD": 720, "FULLHD": 1080, "QUAD": 1440, "UHD": 2160}


def resolution_lines(name):
    key = "".join(ch for ch in str(name).upper() if ch.isalnum())
    if key not in RESOLUTIONS:
        raise ValueError("resolução inválida: %r (use SD, HD, FULL HD, QUAD ou UHD)" % (name,))
    return RESOLUTIONS[key]


class Region:
    """Retângulo livre.
    x, y, width, height : posição e tamanho.
    unit   : 'px' (pixels da janela Kivy) ou 'rel' (0..1 da janela).
    origin : 'top-left' (padrão, como em editores de imagem) ou
             'bottom-left' (coordenadas nativas do Kivy).
    width/height = None estendem até a borda da janela."""

    def __init__(self, x=0, y=0, width=None, height=None, unit="px",
                 origin="top-left", w=None, h=None):
        if unit not in ("px", "rel"):
            raise ValueError("unit deve ser 'px' ou 'rel'")
        if origin not in ("top-left", "bottom-left"):
            raise ValueError("origin deve ser 'top-left' ou 'bottom-left'")
        self.x, self.y = x, y
        self.width = width if width is not None else w
        self.height = height if height is not None else h
        self.unit, self.origin = unit, origin

    @classmethod
    def from_any(cls, v):
        """Aceita Region, (x, y, w, h) ou {'x':..,'y':..,'width'|'w':..,'height'|'h':..}."""
        if v is None or isinstance(v, cls):
            return v
        if isinstance(v, dict):
            return cls(**v)
        v = tuple(v)
        if len(v) != 4:
            raise ValueError("região = (x, y, largura, altura)")
        return cls(*v)

    def resolve(self, win_w, win_h):
        """-> (x, y, w, h) em unidades da janela, origem topo-esquerda."""
        kx, ky = (win_w, win_h) if self.unit == "rel" else (1, 1)
        x, y = self.x * kx, self.y * ky
        w = (win_w - x) if self.width is None else self.width * kx
        h = (win_h - y) if self.height is None else self.height * ky
        if self.origin == "bottom-left":
            y = win_h - (y + h)
        return x, y, w, h

    def __repr__(self):
        return "Region(%r, %r, %r, %r, unit=%r, origin=%r)" % (
            self.x, self.y, self.width, self.height, self.unit, self.origin)


class Target:
    """O que capturar + como entregar.
    region   : Region (ou None)         widget : widget Kivy (ou None)
    isolated : True = renderiza só o widget (mesmo coberto/fora da tela);
               False = copia a área do widget como aparece na tela (rápido)
    size     : (w, h) de saída; um dos lados pode ser None (mantém proporção)
    scale    : fator de escala da saída (ex.: 0.5)"""

    def __init__(self, region=None, widget=None, isolated=False, size=None, scale=1.0,
                 resolution=None):
        self.region = Region.from_any(region)
        self.widget = widget
        self.isolated = bool(isolated)
        self.size = tuple(size) if size else None
        self.scale = scale if scale else 1.0
        if resolution is not None:
            resolution_lines(resolution)
        self.resolution = resolution

    def derive(self, region=None, widget=None, isolated=None, size=None,
               scale=None, fullscreen=False, resolution=None):
        t = Target(self.region, self.widget, self.isolated, self.size, self.scale,
                   self.resolution)
        if fullscreen:
            t.region = t.widget = None
        if region is not None:
            t.region, t.widget = Region.from_any(region), None
        if widget is not None:
            t.widget, t.region = widget, None
        if isolated is not None:
            t.isolated = bool(isolated)
        if size is not None:
            t.size, t.resolution = tuple(size), None
        if scale is not None:
            t.scale, t.size, t.resolution = scale, None, None
        if resolution is not None:
            resolution_lines(resolution)
            t.resolution, t.size = resolution, None
        return t


def resolve_rect(target, win_w, win_h, fb_w, fb_h):
    """Retângulo pedido em pixels do framebuffer, origem topo-esquerda.
    O widget é relido a cada chamada, então a captura acompanha o elemento."""
    if target.widget is not None:
        wd = target.widget
        x, y = wd.to_window(wd.x, wd.y)
        w, h = wd.width, wd.height
        ux, uy, uw, uh = x, win_h - (y + h), w, h
    elif target.region is not None:
        ux, uy, uw, uh = target.region.resolve(win_w, win_h)
    else:
        ux, uy, uw, uh = 0, 0, win_w, win_h
    kx, ky = fb_w / float(win_w), fb_h / float(win_h)
    return (int(round(ux * kx)), int(round(uy * ky)),
            max(1, int(round(uw * kx))), max(1, int(round(uh * ky))))


def clamp_rect(rect, fb_w, fb_h):
    """Recorta ao framebuffer. -> ((x,y,w,h), (offset_x, offset_y)) ou None."""
    x, y, w, h = rect
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(fb_w, x + w), min(fb_h, y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0), (x0 - x, y0 - y)


def output_size(rw, rh, size=None, scale=1.0, even=False, resolution=None):
    """Tamanho final do arquivo."""
    if size:
        w, h = size
        if w and not h:
            h = rh * w / float(rw)
        elif h and not w:
            w = rw * h / float(rh)
        elif not w and not h:
            w, h = rw * scale, rh * scale
    elif resolution is not None:
        lines = resolution_lines(resolution)
        short = min(rw, rh)
        f = lines / float(short) if short > lines else 1.0
        w, h = rw * f, rh * f
    else:
        w, h = rw * scale, rh * scale
    w, h = max(2, int(round(w))), max(2, int(round(h)))
    if even:
        w, h = max(2, w - w % 2), max(2, h - h % 2)
    return w, h
