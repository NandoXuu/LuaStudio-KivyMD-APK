# -*- coding: utf-8 -*-
"""HDR do LuaStudio: configuracao (`Graphics.HDR`), matematica de referencia
(PQ/ST 2084, BT.2020, tone mapping), shader de resolve e deteccao do display
(Android via jnius, Windows via DisplayConfig).

Fluxo de um frame com HDR ligado:

    cena (Fbo float) -> postfx -> RESOLVE (este modulo) -> janela

O resolve le a cena, linearizada e em unidades de "branco de papel"
(1.0 = PaperWhiteNits), expande os realces (opcional), aplica o tone mapping
ate o teto do display (PeakLuminanceNits / PaperWhiteNits), converte pro
gamut de saida e codifica em PQ. Quando o display ou a superficie nativa nao
confirmam HDR10, a saida cai pra SDR sem quebrar o jogo (ver `HDRState.mode`).
"""

import math
import os
import sys
import threading

from . import glsl as glsl_mod

RESOLVE_NAME = "__hdr_resolve__"

OUTPUTS = ("HDR10", "SDR")
COLOR_SPACES = ("BT2020", "P3", "BT709")
TRANSFERS = ("PQ", "Linear")
TONE_MAPPERS = ("ACES", "Reinhard", "Hable", "None")

PAPER_WHITE_MIN, PAPER_WHITE_MAX = 80.0, 1000.0
PEAK_MIN, PEAK_MAX = 100.0, 10000.0

_ALIASES = {
    "output": {"hdr10": "HDR10", "hdr": "HDR10", "pq": "HDR10", "sdr": "SDR", "off": "SDR", "none": "SDR"},
    "color_space": {"bt2020": "BT2020", "bt.2020": "BT2020", "rec2020": "BT2020", "rec.2020": "BT2020",
                    "p3": "P3", "displayp3": "P3", "display-p3": "P3", "dcip3": "P3",
                    "bt709": "BT709", "bt.709": "BT709", "rec709": "BT709", "srgb": "BT709"},
    "transfer_function": {"pq": "PQ", "st2084": "PQ", "smpte2084": "PQ", "smpte st 2084": "PQ",
                          "linear": "Linear", "scrgb": "Linear"},
    "tone_mapping": {"aces": "ACES", "filmic": "ACES", "reinhard": "Reinhard",
                     "hable": "Hable", "uncharted2": "Hable",
                     "none": "None", "off": "None", "clip": "None", "linear": "None"},
}

_METADATA_KEYS = ("max_cll", "max_fall", "mastering_min_nits", "mastering_max_nits")


def default_hdr_config():
    return {
        "enabled": False,
        "output": "HDR10",
        "color_space": "BT2020",
        "transfer_function": "PQ",
        "paper_white_nits": 203.0,
        "peak_luminance_nits": 1000.0,
        "tone_mapping": "None",
        "exposure": 1.0,
        "expand_highlights": 0.0,
        "preview": False,
        "assume_pq_surface": False,
        "metadata": {"max_cll": 0.0, "max_fall": 0.0,
                     "mastering_min_nits": 0.0001, "mastering_max_nits": 1000.0},
    }


def _num(value):
    if isinstance(value, bool):
        raise ValueError("booleano")
    return float(value)


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _flag(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes", "sim")
    return bool(value)


def normalize_hdr(cfg, base=None, problems=None):
    """Valida `cfg` (chaves em snake_case) em cima de `base`. Valor invalido
    nao derruba nada: mantem o anterior e, se `problems` for uma lista,
    anota o motivo."""
    out = dict(base) if base else default_hdr_config()
    out["metadata"] = dict(out.get("metadata") or default_hdr_config()["metadata"])
    if not isinstance(cfg, dict):
        return out

    def bad(key, value, why):
        if problems is not None:
            problems.append("valor invalido para %s: %r (%s)" % (key, value, why))

    for key in ("enabled", "preview", "assume_pq_surface"):
        if key in cfg:
            out[key] = _flag(cfg[key])
    for key, table in _ALIASES.items():
        if key in cfg:
            canon = table.get(str(cfg[key]).strip().lower())
            if canon is None:
                bad(key, cfg[key], "use um de %s" % ", ".join(sorted(set(table.values()))))
            else:
                out[key] = canon
    numeric = (("paper_white_nits", PAPER_WHITE_MIN, PAPER_WHITE_MAX),
               ("peak_luminance_nits", PEAK_MIN, PEAK_MAX),
               ("exposure", 0.0, 16.0),
               ("expand_highlights", 0.0, 1.0))
    for key, lo, hi in numeric:
        if key in cfg:
            try:
                val = _num(cfg[key])
                if val != val or val in (float("inf"), float("-inf")):
                    raise ValueError("nao finito")
                if not lo <= val <= hi:
                    bad(key, cfg[key], "ajustado para %g..%g" % (lo, hi))
                out[key] = _clamp(val, lo, hi)
            except (TypeError, ValueError):
                bad(key, cfg[key], "numero esperado")
    meta_in = dict(cfg["metadata"]) if isinstance(cfg.get("metadata"), dict) else {}
    for key in _METADATA_KEYS:
        if key in cfg:
            meta_in[key] = cfg[key]
    for key, value in meta_in.items():
        if key not in _METADATA_KEYS:
            continue
        try:
            val = _num(value)
            if val != val or val < 0 or val > PEAK_MAX:
                raise ValueError("fora da faixa")
            out["metadata"][key] = val
        except (TypeError, ValueError):
            bad(key, value, "numero entre 0 e %g" % PEAK_MAX)
    if out["peak_luminance_nits"] < out["paper_white_nits"]:
        out["peak_luminance_nits"] = out["paper_white_nits"]
    return out


# ------------------------------------------------------------ matematica
PQ_M1 = 2610.0 / 16384.0
PQ_M2 = 2523.0 / 4096.0 * 128.0
PQ_C1 = 3424.0 / 4096.0
PQ_C2 = 2413.0 / 4096.0 * 32.0
PQ_C3 = 2392.0 / 4096.0 * 32.0
PQ_MAX_NITS = 10000.0

BT709_TO_BT2020 = ((0.6274040, 0.3292820, 0.0433136),
                   (0.0690970, 0.9195400, 0.0113612),
                   (0.0163916, 0.0880132, 0.8955950))
BT709_TO_P3 = ((0.8224621, 0.1775380, 0.0000000),
               (0.0331941, 0.9668058, 0.0000000),
               (0.0170827, 0.0723974, 0.9105199))
BT709_IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
GAMUT_MATRICES = {"BT2020": BT709_TO_BT2020, "P3": BT709_TO_P3, "BT709": BT709_IDENTITY}
GAMUT_INDEX = {"BT709": 0.0, "P3": 1.0, "BT2020": 2.0}


def pq_encode(nits):
    y = _clamp(float(nits), 0.0, PQ_MAX_NITS) / PQ_MAX_NITS
    p = max(y, 1e-9) ** PQ_M1
    return ((PQ_C1 + PQ_C2 * p) / (1.0 + PQ_C3 * p)) ** PQ_M2


def pq_decode(code):
    e = _clamp(float(code), 0.0, 1.0) ** (1.0 / PQ_M2)
    num = max(e - PQ_C1, 0.0)
    den = PQ_C2 - PQ_C3 * e
    return PQ_MAX_NITS * (num / den) ** (1.0 / PQ_M1) if den > 0 else PQ_MAX_NITS


def srgb_to_linear(c):
    a = abs(c)
    v = a / 12.92 if a <= 0.04045 else ((a + 0.055) / 1.055) ** 2.4
    return math.copysign(v, c)


def linear_to_srgb(c):
    c = _clamp(c, 0.0, 1.0)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055


def apply_matrix(m, rgb):
    return tuple(m[i][0] * rgb[0] + m[i][1] * rgb[1] + m[i][2] * rgb[2] for i in range(3))


def _op_aces(v):
    return (v * (2.51 * v + 0.03)) / (v * (2.43 * v + 0.59) + 0.14)


def _op_reinhard(v):
    return v / (1.0 + v)


def _op_hable(x):
    a, b, c, d, e, f = 0.15, 0.50, 0.10, 0.20, 0.02, 0.30
    return ((x * (a * x + c * b) + d * e) / (x * (a * x + b) + d * f)) - e / f


_OPERATORS = {"ACES": (1.0, _op_aces, 2.51 / 2.43),
              "Reinhard": (2.0, _op_reinhard, 1.0),
              "Hable": (3.0, _op_hable, 1.0 - 0.02 / 0.30)}

_SDR_SCALE_ASYM = {"ACES": (1.0, 1.0), "Reinhard": (1.0, 1.0),
                   "Hable": (2.0, None)}  # asym do Hable SDR = op(11.2)


def tonemap_params(name, headroom):
    """Parametros do tone mapping HDR: `out = H * op(x * scale) / asym`,
    com `scale` resolvido pra que o branco de papel (x = 1) continue em 1.0
    e o infinito caia exatamente no teto H. 'None' so corta no teto."""
    h = max(1.0, float(headroom))
    spec = _OPERATORS.get(name)
    if spec is None or h <= 1.0005:
        return {"kind": 0.0, "scale": 1.0, "asym": 1.0, "headroom": h}
    kind, op, asym = spec
    target = asym / h
    lo, hi = 0.0, 1.0
    while op(hi) < target and hi < 1e6:
        hi *= 2.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if op(mid) < target:
            lo = mid
        else:
            hi = mid
    return {"kind": kind, "scale": (lo + hi) / 2.0, "asym": asym, "headroom": h}


def tonemap_params_sdr(name):
    """Tone mapping classico (sem ancora no branco) pra saida SDR/preview."""
    spec = _OPERATORS.get(name)
    if spec is None:
        return {"kind": 0.0, "scale": 1.0, "asym": 1.0, "headroom": 1.0}
    kind, op, _asym = spec
    scale, asym = _SDR_SCALE_ASYM[name]
    if asym is None:
        asym = op(11.2)
    return {"kind": kind, "scale": scale, "asym": asym, "headroom": 1.0}


def tonemap(x, params):
    x = max(0.0, float(x))
    h = params["headroom"]
    kind = params["kind"]
    if kind < 0.5:
        return min(x, h)
    op = {1.0: _op_aces, 2.0: _op_reinhard, 3.0: _op_hable}[kind]
    return min(h * op(x * params["scale"]) / params["asym"], h)


def _smoothstep(e0, e1, x):
    t = _clamp((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def expand_gain(luma_max, expand_range):
    t = _smoothstep(0.5, 1.0, luma_max) * _clamp(2.0 - luma_max, 0.0, 1.0)
    return 1.0 + expand_range * t * t


def resolve_pixel(rgb, uniforms):
    """Referencia em Python do shader de resolve (mesma ordem de passos).
    `rgb`: cor da cena como o Kivy a desenha (sRGB, pode passar de 1.0)."""
    lin = [srgb_to_linear(c) * uniforms["uExposure"] for c in rgb[:3]]
    lin = [c * expand_gain(max(lin), uniforms["uExpandRange"]) for c in lin]
    params = {"kind": uniforms["uTmKind"], "scale": uniforms["uTmScale"],
              "asym": uniforms["uTmAsym"], "headroom": uniforms["uOutHeadroom"]}
    lin = [tonemap(c, params) for c in lin]
    mode = uniforms["uHdrMode"]
    if mode < 0.5:
        return tuple(linear_to_srgb(c) for c in lin)
    if uniforms["uColorSpace"] > 1.5:
        mat = BT709_TO_BT2020
    elif uniforms["uColorSpace"] > 0.5:
        mat = BT709_TO_P3
    else:
        mat = BT709_IDENTITY
    lin = apply_matrix(mat, lin)
    nits = [c * uniforms["uPaperWhite"] for c in lin]
    if mode < 1.5:
        return tuple(pq_encode(n) for n in nits)
    return tuple(n / 80.0 for n in nits)


# ---------------------------------------------------------------- shader
RESOLVE_FRAGMENT = """
uniform float uHdrMode;
uniform float uExposure;
uniform float uExpandRange;
uniform float uOutHeadroom;
uniform float uPaperWhite;
uniform float uColorSpace;
uniform float uTmKind;
uniform float uTmScale;
uniform float uTmAsym;

vec3 srgbToLinear(vec3 c)
{
    vec3 a = abs(c);
    vec3 lo = a / 12.92;
    vec3 hi = pow((a + 0.055) / 1.055, vec3(2.4));
    return sign(c) * mix(hi, lo, step(a, vec3(0.04045)));
}

vec3 linearToSrgb(vec3 c)
{
    c = clamp(c, 0.0, 1.0);
    vec3 lo = c * 12.92;
    vec3 hi = 1.055 * pow(max(c, vec3(0.0031308)), vec3(1.0 / 2.4)) - 0.055;
    return mix(hi, lo, step(c, vec3(0.0031308)));
}

vec3 opAces(vec3 v) { return (v * (2.51 * v + 0.03)) / (v * (2.43 * v + 0.59) + 0.14); }
vec3 opReinhard(vec3 v) { return v / (1.0 + v); }
vec3 opHable(vec3 x)
{
    float A = 0.15; float B = 0.50; float C = 0.10;
    float D = 0.20; float E = 0.02; float F = 0.30;
    return ((x * (A * x + C * B) + D * E) / (x * (A * x + B) + D * F)) - E / F;
}

vec3 toneMap(vec3 x)
{
    x = max(x, vec3(0.0));
    if (uTmKind < 0.5)
        return min(x, vec3(uOutHeadroom));
    vec3 v = x * uTmScale;
    vec3 o;
    if (uTmKind < 1.5) o = opAces(v);
    else if (uTmKind < 2.5) o = opReinhard(v);
    else o = opHable(v);
    return min(uOutHeadroom * o / uTmAsym, vec3(uOutHeadroom));
}

vec3 toGamut(vec3 c)
{
    if (uColorSpace > 1.5)
        return vec3(dot(vec3(0.6274040, 0.3292820, 0.0433136), c),
                    dot(vec3(0.0690970, 0.9195400, 0.0113612), c),
                    dot(vec3(0.0163916, 0.0880132, 0.8955950), c));
    if (uColorSpace > 0.5)
        return vec3(dot(vec3(0.8224621, 0.1775380, 0.0), c),
                    dot(vec3(0.0331941, 0.9668058, 0.0), c),
                    dot(vec3(0.0170827, 0.0723974, 0.9105199), c));
    return c;
}

vec3 pqEncode(vec3 nits)
{
    vec3 y = clamp(nits / 10000.0, vec3(1e-9), vec3(1.0));
    vec3 p = pow(y, vec3(0.1593017578125));
    return pow((0.8359375 + 18.8515625 * p) / (1.0 + 18.6875 * p), vec3(78.84375));
}

void main(void)
{
    vec4 src = texture2D(texture0, tex_coord0);
    vec3 lin = srgbToLinear(src.rgb) * uExposure;
    float peak = max(max(lin.r, lin.g), lin.b);
    float t = smoothstep(0.5, 1.0, peak) * clamp(2.0 - peak, 0.0, 1.0);
    lin *= 1.0 + uExpandRange * t * t;
    lin = toneMap(lin);
    if (uHdrMode < 0.5) {
        gl_FragColor = vec4(linearToSrgb(lin), src.a);
    } else if (uHdrMode < 1.5) {
        gl_FragColor = vec4(pqEncode(toGamut(lin) * uPaperWhite), src.a);
    } else {
        gl_FragColor = vec4(toGamut(lin) * (uPaperWhite / 80.0), src.a);
    }
}
"""

glsl_mod.SHADERS.register(RESOLVE_NAME, RESOLVE_FRAGMENT)


# --------------------------------------------------------------- display
HDR_TYPE_NAMES = {1: "DolbyVision", 2: "HDR10", 3: "HLG", 4: "HDR10+"}


def _empty_caps(platform, reason):
    return {"platform": platform, "supported": False, "types": [], "max_nits": None,
            "max_avg_nits": None, "min_nits": None, "wide_gamut": False,
            "sdr_white_nits": None, "reason": reason}


class Backend(object):
    """Contrato de um backend de plataforma. `surface_ready` so vira True
    quando a superficie da janela esta realmente marcada como BT.2020/PQ."""
    name = "null"
    surface_ready = False

    def probe(self):
        return _empty_caps(sys.platform, "esta plataforma nao expoe consulta de HDR")

    def activate(self, cfg, caps):
        return False, "backend sem saida HDR10 nativa"

    def deactivate(self):
        self.surface_ready = False

    def apply_metadata(self, meta):
        return False


class AndroidBackend(Backend):
    """Consulta a tela via jnius (Display.getHdrCapabilities / isHdr) e tenta
    colocar a janela em COLOR_MODE_HDR + dataspace BT2020_PQ na superficie."""
    name = "android"
    COLOR_MODE_DEFAULT = 0
    COLOR_MODE_HDR = 2
    DATASPACE_BT2020_PQ = 163971072

    def __init__(self, log=None):
        self.log = log or (lambda s: None)
        self._activity = None
        self._color_mode_set = False
        self._dataspace_set = False

    def _jnius(self):
        from jnius import autoclass
        return autoclass

    def _display(self, autoclass):
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        self._activity = activity
        display = None
        try:
            display = activity.getDisplay()
        except Exception:
            display = None
        if display is None:
            display = activity.getWindowManager().getDefaultDisplay()
        return display

    def probe(self):
        caps = _empty_caps("android", "")
        try:
            autoclass = self._jnius()
            sdk = int(autoclass("android.os.Build$VERSION").SDK_INT)
            display = self._display(autoclass)
        except Exception as ex:
            caps["reason"] = "jnius/Display indisponivel (%s: %s)" % (type(ex).__name__, ex)
            return caps
        types = []
        try:
            if sdk >= 24:
                hc = display.getHdrCapabilities()
                if hc is not None:
                    types = [int(t) for t in (hc.getSupportedHdrTypes() or [])]
                    for key, fn in (("max_nits", "getDesiredMaxLuminance"),
                                    ("max_avg_nits", "getDesiredMaxAverageLuminance"),
                                    ("min_nits", "getDesiredMinLuminance")):
                        val = float(getattr(hc, fn)())
                        caps[key] = val if val > 0 else None
            if sdk >= 34:
                try:
                    more = [int(t) for t in (display.getMode().getSupportedHdrTypes() or [])]
                    types = sorted(set(types) | set(more))
                except Exception:
                    pass
        except Exception as ex:
            caps["reason"] = "HdrCapabilities falhou (%s: %s)" % (type(ex).__name__, ex)
        try:
            if sdk >= 26:
                caps["wide_gamut"] = bool(display.isWideColorGamut())
                is_hdr = bool(display.isHdr())
            else:
                is_hdr = bool(types)
        except Exception:
            is_hdr = bool(types)
        caps["types"] = [HDR_TYPE_NAMES.get(t, str(t)) for t in types]
        caps["supported"] = is_hdr and (2 in types or 4 in types)
        if not caps["supported"] and not caps["reason"]:
            if sdk < 24:
                caps["reason"] = "Android %d: sem API de HDR (precisa 7.0+)" % sdk
            elif not types:
                caps["reason"] = "a tela nao reporta tipos de HDR"
            else:
                caps["reason"] = "a tela nao suporta HDR10 (tipos: %s)" % ", ".join(caps["types"])
        return caps

    def _on_ui_thread(self, fn, timeout=3.0):
        from android.runnable import run_on_ui_thread
        done = threading.Event()
        box = {}

        @run_on_ui_thread
        def runner():
            try:
                box["value"] = fn()
            except Exception as ex:
                box["error"] = ex
            done.set()
        runner()
        if not done.wait(timeout):
            raise RuntimeError("a UI thread do Android nao respondeu")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def _surface_view(self, autoclass):
        sdl = autoclass("org.libsdl.app.SDLActivity")
        layout = sdl.getContentView()
        for i in range(int(layout.getChildCount())):
            child = layout.getChildAt(i)
            if child is not None and str(child.getClass().getName()).endswith("SDLSurface"):
                return child
        raise RuntimeError("SDLSurface nao encontrada")

    def activate(self, cfg, caps):
        try:
            autoclass = self._jnius()
            sdk = int(autoclass("android.os.Build$VERSION").SDK_INT)
            self._display(autoclass)
        except Exception as ex:
            return False, "jnius indisponivel (%s: %s)" % (type(ex).__name__, ex)
        if sdk < 26:
            return False, "Android %d: Window.setColorMode exige 8.0+" % sdk
        activity = self._activity
        mode = self.COLOR_MODE_HDR

        def set_mode():
            activity.getWindow().setColorMode(mode)
            return int(activity.getWindow().getColorMode())
        try:
            got = self._on_ui_thread(set_mode)
            self._color_mode_set = True
        except Exception as ex:
            return False, "setColorMode(HDR) falhou (%s: %s)" % (type(ex).__name__, ex)
        if got != mode:
            return False, "o sistema recusou COLOR_MODE_HDR (ficou %s)" % got
        if sdk < 34:
            return False, ("Android %d: marcar a superficie como BT.2020/PQ exige a API 34 "
                           "(SurfaceControl.Transaction.setDataSpace); use AssumePQSurface "
                           "se a sua camada nativa ja faz isso" % sdk)
        try:
            self._on_ui_thread(lambda: self._set_dataspace(autoclass, self.DATASPACE_BT2020_PQ))
            self._dataspace_set = True
        except Exception as ex:
            return False, "setDataSpace(BT2020_PQ) falhou (%s: %s)" % (type(ex).__name__, ex)
        self.surface_ready = True
        return True, ""

    def _set_dataspace(self, autoclass, dataspace):
        view = self._surface_view(autoclass)
        control = view.getSurfaceControl()
        if control is None or not control.isValid():
            raise RuntimeError("SurfaceControl invalido (superficie ainda nao criada)")
        txn = autoclass("android.view.SurfaceControl$Transaction")()
        try:
            txn.setDataSpace(control, dataspace)
            txn.apply()
        finally:
            txn.close()

    def deactivate(self):
        autoclass = None
        try:
            autoclass = self._jnius()
            if self._dataspace_set:
                self._on_ui_thread(lambda: self._set_dataspace(autoclass, 0))
            if self._color_mode_set and self._activity is not None:
                act, mode = self._activity, self.COLOR_MODE_DEFAULT
                self._on_ui_thread(lambda: act.getWindow().setColorMode(mode))
        except Exception as ex:
            self.log("[HDR] restaurar a janela falhou (%s: %s)" % (type(ex).__name__, ex))
        self._color_mode_set = False
        self._dataspace_set = False
        self.surface_ready = False

    def apply_metadata(self, meta):
        return False


class WindowsBackend(Backend):
    """Consulta o Advanced Color do monitor via DisplayConfig. A saida HDR10
    em si exige uma swapchain DXGI (R10G10B10A2 + ST 2084) que o SDL2/Kivy
    nao cria; por isso `surface_ready` so vira True com AssumePQSurface."""
    name = "windows"

    def probe(self):
        caps = _empty_caps("windows", "")
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
        except Exception as ex:
            caps["reason"] = "ctypes/user32 indisponivel (%s: %s)" % (type(ex).__name__, ex)
            return caps

        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

        class Header(ctypes.Structure):
            _fields_ = [("type", ctypes.c_uint32), ("size", ctypes.c_uint32),
                        ("adapterId", LUID), ("id", ctypes.c_uint32)]

        class Rational(ctypes.Structure):
            _fields_ = [("num", ctypes.c_uint32), ("den", ctypes.c_uint32)]

        class Source(ctypes.Structure):
            _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32),
                        ("modeInfoIdx", ctypes.c_uint32), ("statusFlags", ctypes.c_uint32)]

        class Target(ctypes.Structure):
            _fields_ = [("adapterId", LUID), ("id", ctypes.c_uint32),
                        ("modeInfoIdx", ctypes.c_uint32), ("outputTechnology", ctypes.c_uint32),
                        ("rotation", ctypes.c_uint32), ("scaling", ctypes.c_uint32),
                        ("refreshRate", Rational), ("scanLineOrdering", ctypes.c_uint32),
                        ("targetAvailable", ctypes.c_int32), ("statusFlags", ctypes.c_uint32)]

        class Path(ctypes.Structure):
            _fields_ = [("sourceInfo", Source), ("targetInfo", Target), ("flags", ctypes.c_uint32)]

        class Mode(ctypes.Structure):
            _fields_ = [("raw", ctypes.c_ubyte * 64)]

        class AdvancedColor(ctypes.Structure):
            _fields_ = [("header", Header), ("value", ctypes.c_uint32),
                        ("colorEncoding", ctypes.c_uint32), ("bitsPerColorChannel", ctypes.c_uint32)]

        class SdrWhite(ctypes.Structure):
            _fields_ = [("header", Header), ("level", ctypes.c_uint32)]

        try:
            n_paths, n_modes = ctypes.c_uint32(0), ctypes.c_uint32(0)
            qdc_active = 0x2
            if user32.GetDisplayConfigBufferSizes(qdc_active, ctypes.byref(n_paths), ctypes.byref(n_modes)) != 0:
                raise OSError("GetDisplayConfigBufferSizes falhou")
            paths = (Path * max(1, n_paths.value))()
            modes = (Mode * max(1, n_modes.value))()
            if user32.QueryDisplayConfig(qdc_active, ctypes.byref(n_paths), paths,
                                         ctypes.byref(n_modes), modes, None) != 0:
                raise OSError("QueryDisplayConfig falhou")
            if n_paths.value == 0:
                caps["reason"] = "nenhum monitor ativo encontrado"
                return caps
            target = paths[0].targetInfo
            adv = AdvancedColor()
            adv.header.type = 9
            adv.header.size = ctypes.sizeof(AdvancedColor)
            adv.header.adapterId = target.adapterId
            adv.header.id = target.id
            if user32.DisplayConfigGetDeviceInfo(ctypes.byref(adv)) != 0:
                raise OSError("DisplayConfigGetDeviceInfo(ADVANCED_COLOR_INFO) falhou")
            supported, enabled = bool(adv.value & 0x1), bool(adv.value & 0x2)
            caps["wide_gamut"] = bool(adv.value & 0x4) or supported
            caps["supported"] = supported and enabled
            caps["types"] = ["HDR10"] if caps["supported"] else []
            if supported and not enabled:
                caps["reason"] = "o monitor tem HDR, mas ele esta desligado em Configuracoes > Tela > HDR"
            elif not supported:
                caps["reason"] = "o monitor/driver nao reporta Advanced Color (HDR)"
            white = SdrWhite()
            white.header.type = 11
            white.header.size = ctypes.sizeof(SdrWhite)
            white.header.adapterId = target.adapterId
            white.header.id = target.id
            if user32.DisplayConfigGetDeviceInfo(ctypes.byref(white)) == 0 and white.level:
                caps["sdr_white_nits"] = white.level / 1000.0 * 80.0
        except Exception as ex:
            caps["reason"] = "DisplayConfig falhou (%s: %s)" % (type(ex).__name__, ex)
        return caps

    def activate(self, cfg, caps):
        return False, ("Windows: a swapchain HDR10 (DXGI R10G10B10A2 + ST 2084) precisa da camada "
                       "nativa; o SDL2/Kivy entrega uma superficie de 8 bits sRGB")


def default_backend(log=None):
    from . import permissions as perms
    if perms.ANDROID:
        return AndroidBackend(log)
    if sys.platform == "win32":
        return WindowsBackend()
    return Backend()


# ----------------------------------------------------------------- estado
class HDRState(object):
    """Estado de HDR de um Runtime: decide o modo de saida do frame e
    entrega ao Stage o passe de resolve com seus uniforms."""

    def __init__(self, runtime):
        self.rt = runtime
        self.backend = None
        self.allow_native_output = False
        self.mode = "off"
        self.reason = ""
        self.internal_format = "unknown"
        self._caps = None
        self._last_summary = None
        self._metadata_applied = False

    # ---- config
    @property
    def cfg(self):
        return self.rt.render["hdr"]

    def _get_backend(self):
        if self.backend is None:
            self.backend = default_backend(self.rt.log)
        return self.backend

    def set_backend(self, backend):
        if self.backend is not None and self.mode == "hdr10":
            self.backend.deactivate()
        self.backend = backend
        self._caps = None
        self.refresh()

    def capabilities(self, force=False):
        if self._caps is None or force:
            try:
                self._caps = self._get_backend().probe()
            except Exception as ex:
                self._caps = _empty_caps(sys.platform, "consulta HDR falhou (%s: %s)" % (type(ex).__name__, ex))
        return self._caps

    def is_supported(self):
        return bool(self.capabilities()["supported"])

    # ---- niveis
    def peak_nits(self):
        cfg = self.cfg
        peak = cfg["peak_luminance_nits"]
        detected = self._caps.get("max_nits") if self._caps else None
        if detected:
            peak = min(peak, detected)
        return max(peak, cfg["paper_white_nits"])

    def headroom(self):
        return self.peak_nits() / self.cfg["paper_white_nits"]

    # ---- decisao do modo
    def refresh(self, reprobe=False):
        cfg = self.cfg
        old_mode = self.mode
        reason = ""
        mode = "off"
        if not cfg["enabled"]:
            reason = "HDR desligado (Graphics.HDR.Enabled = false)"
        else:
            caps = self.capabilities(force=reprobe)
            wants_hdr10 = cfg["output"] == "HDR10"
            if not wants_hdr10:
                reason = "Output = SDR"
            elif not self.allow_native_output:
                reason = "saida HDR10 so existe no Player (a IDE desenha junto com a interface SDR)"
            elif not caps["supported"] and not cfg["assume_pq_surface"]:
                reason = caps["reason"] or "o display nao suporta HDR10"
            else:
                ready, why = self._ensure_surface(cfg, caps)
                if ready:
                    mode = "hdr10"
                else:
                    reason = why
            if mode != "hdr10" and cfg["preview"]:
                mode = "preview"
                reason = (reason + "; " if reason else "") + "pipeline HDR rodando em modo Preview (saida SDR)"
        if mode != "hdr10" and old_mode == "hdr10":
            self._release_surface()
        self.mode = mode
        self.reason = reason
        self._sync_lighting()
        self._log_summary()

    def _ensure_surface(self, cfg, caps):
        backend = self._get_backend()
        if cfg["assume_pq_surface"]:
            self._apply_metadata()
            return True, ""
        if backend.surface_ready:
            return True, ""
        try:
            ok, why = backend.activate(cfg, caps)
        except Exception as ex:
            ok, why = False, "ativar HDR nativo falhou (%s: %s)" % (type(ex).__name__, ex)
        if ok:
            self._apply_metadata()
        return ok, why

    def _release_surface(self):
        if self.backend is not None:
            try:
                self.backend.deactivate()
            except Exception as ex:
                self.rt.log("[HDR] desativar falhou (%s: %s)" % (type(ex).__name__, ex))
        self._metadata_applied = False

    def _apply_metadata(self):
        if self.backend is None:
            return
        try:
            self._metadata_applied = bool(self.backend.apply_metadata(self.resolved_metadata()))
        except Exception:
            self._metadata_applied = False

    def resolved_metadata(self):
        """Metadados HDR10 estaticos (ST 2086 + CTA-861.3), separados da
        configuracao de render: 0 em MaxCLL/MaxFALL significa 'desconhecido'."""
        meta = dict(self.cfg["metadata"])
        meta["mastering_max_nits"] = max(meta["mastering_max_nits"], meta["mastering_min_nits"])
        meta["primaries"] = "BT2020"
        meta["white_point"] = "D65"
        return meta

    def _sync_lighting(self):
        from . import lighting
        lighting.COLOR_CEILING = self.headroom() if self.mode != "off" else 1.0

    def _log_summary(self):
        cfg = self.cfg
        summary = (self.mode, cfg["enabled"], self.reason)
        if summary == self._last_summary:
            return
        self._last_summary = summary
        if self.mode == "hdr10":
            self.rt.log("[HDR] HDR10 ativo: %s/%s, branco de papel %d nits, pico %d nits, tone mapping %s"
                        % (cfg["color_space"], cfg["transfer_function"], cfg["paper_white_nits"],
                           self.peak_nits(), cfg["tone_mapping"]))
        elif cfg["enabled"]:
            self.rt.log("[HDR] solicitado, saida em SDR: %s" % self.reason)

    # ---- frame
    def wants_float_buffers(self):
        return self.mode != "off"

    def report_internal_format(self, fmt, reason=""):
        if fmt != self.internal_format:
            self.internal_format = fmt
            if fmt == "8bit":
                self.rt.log("[HDR] buffer float indisponivel (%s): pipeline interno em 8 bits, "
                            "sem realces acima de 1.0 vindos da cena" % (reason or "sem motivo"))

    def uniforms(self):
        cfg = self.cfg
        h = self.headroom()
        mode = self.mode
        if mode == "hdr10":
            out_mode = 1.0 if cfg["transfer_function"] == "PQ" else 2.0
            tm = tonemap_params(cfg["tone_mapping"], h)
        else:
            out_mode = 0.0
            tm = tonemap_params_sdr(cfg["tone_mapping"])
        return {
            "uHdrMode": out_mode,
            "uExposure": cfg["exposure"],
            "uExpandRange": cfg["expand_highlights"] * (h - 1.0),
            "uOutHeadroom": tm["headroom"],
            "uPaperWhite": cfg["paper_white_nits"],
            "uColorSpace": GAMUT_INDEX[cfg["color_space"]],
            "uTmKind": tm["kind"],
            "uTmScale": tm["scale"],
            "uTmAsym": tm["asym"],
        }

    def plan_entry(self):
        if self.mode == "off":
            return None
        return (RESOLVE_NAME, self.uniforms())

    # ---- Lua
    def capabilities_dict(self):
        caps = self.capabilities()
        return {"Platform": caps["platform"], "Supported": bool(caps["supported"]),
                "Types": list(caps["types"]), "MaxNits": caps["max_nits"],
                "MaxAverageNits": caps["max_avg_nits"], "MinNits": caps["min_nits"],
                "WideColorGamut": bool(caps["wide_gamut"]), "SdrWhiteNits": caps["sdr_white_nits"],
                "Reason": caps["reason"]}

    def status_dict(self):
        cfg = self.cfg
        caps = self.capabilities() if cfg["enabled"] or self._caps else None
        return {
            "Enabled": cfg["enabled"],
            "Active": self.mode == "hdr10",
            "Mode": {"hdr10": "HDR10", "preview": "Preview", "off": "SDR"}[self.mode],
            "Supported": bool(caps["supported"]) if caps else False,
            "Reason": self.reason,
            "InternalFormat": self.internal_format,
            "PaperWhiteNits": cfg["paper_white_nits"],
            "PeakLuminanceNits": self.peak_nits(),
            "Headroom": self.headroom(),
            "MetadataApplied": self._metadata_applied,
        }


# --------------------------------------------------------------- API Lua
def _lua_table(values):
    from .lua import LuaTable
    t = LuaTable()
    for k, v in values.items():
        if isinstance(v, (list, tuple)):
            v = LuaTable(list(v))
        t.set(k, v)
    return t


_PROPS = {
    "Enabled": "enabled", "Output": "output", "ColorSpace": "color_space",
    "TransferFunction": "transfer_function", "PaperWhiteNits": "paper_white_nits",
    "PeakLuminanceNits": "peak_luminance_nits", "ToneMapping": "tone_mapping",
    "Exposure": "exposure", "ExpandHighlights": "expand_highlights",
    "Preview": "preview", "AssumePQSurface": "assume_pq_surface",
}
_META_PROPS = {"MaxCLL": "max_cll", "MaxFALL": "max_fall",
               "MasteringMinNits": "mastering_min_nits", "MasteringMaxNits": "mastering_max_nits"}
_READONLY = ("Active", "Mode", "Reason")


class HDRMetadataAPI(object):
    """`Graphics.HDR.Metadata`: metadados HDR10 estaticos (ST 2086, MaxCLL,
    MaxFALL). Separados das propriedades de render e nao substituem o pipeline."""

    def __init__(self, runtime):
        self.rt = runtime

    def lua_index(self, key):
        k = str(key)
        if k in _META_PROPS:
            return self.rt.render["hdr"]["metadata"][_META_PROPS[k]]
        if k == "Applied":
            return self.rt.hdr._metadata_applied
        return None

    def lua_newindex(self, key, value):
        from .lua import LuaError
        k = str(key)
        if k not in _META_PROPS:
            raise LuaError("Graphics.HDR.Metadata.%s nao existe (use %s)" % (k, ", ".join(sorted(_META_PROPS))))
        self.rt.set_hdr(_META_PROPS[k], value)


class HDRAPI(object):
    """`Graphics.HDR` no Lua."""

    def __init__(self, runtime):
        self.rt = runtime
        self.metadata = HDRMetadataAPI(runtime)

    def lua_index(self, key):
        k = str(key)
        if k in _PROPS:
            return self.rt.render["hdr"][_PROPS[k]]
        if k == "Metadata":
            return self.metadata
        if k == "Active":
            return self.rt.hdr.mode == "hdr10"
        if k == "Mode":
            return self.rt.hdr.status_dict()["Mode"]
        if k == "Reason":
            return self.rt.hdr.reason
        return getattr(self, "m_" + k, None)

    def lua_newindex(self, key, value):
        from .lua import LuaError
        k = str(key)
        if k in _PROPS:
            self.rt.set_hdr(_PROPS[k], value)
        elif k in _READONLY:
            raise LuaError("Graphics.HDR.%s e somente leitura" % k)
        else:
            self.rt.log("[HDR] propriedade desconhecida: Graphics.HDR.%s (use %s)"
                        % (k, ", ".join(sorted(_PROPS))))

    def m_IsSupported(self, *_a):
        return self.rt.hdr.is_supported()

    def m_IsActive(self, *_a):
        return self.rt.hdr.mode == "hdr10"

    def m_GetCapabilities(self, *_a):
        return _lua_table(self.rt.hdr.capabilities_dict())

    def m_GetStatus(self, *_a):
        return _lua_table(self.rt.hdr.status_dict())

    def m_Refresh(self, *_a):
        self.rt.hdr.refresh(reprobe=True)
        return self.rt.hdr.mode == "hdr10"
