# -*- coding: utf-8 -*-
"""Calibracao de cor profissional do LuaStudio (`Graphics.ColorCalibration`).

Funciona em SDR e em HDR. E um passe de tela inteira que roda DEPOIS do
postfx e ANTES do resolve de HDR (ou da saida direta, em SDR):

    cena -> postfx -> CALIBRACAO (este modulo) -> resolve HDR / saida SDR

Como o tone mapping vive no resolve, a calibracao acontece antes dele: os
realces sao comprimidos uma unica vez. Em SDR nao existe tone mapping; o
passe e o ultimo e o resultado e cortado em 0..1 (branco/preto acima do
limite de saida sao recortados, nao inventam detalhe).

Ordem dos ajustes (a ordem importa):

    1. Black Point / White Point   niveis, em valor codificado (sRGB)
    2. Contrast                    em torno do cinza medio, em valor codificado
    3. RGB Gain / RGB Offset       em luz LINEAR (balanco de branco correto)
    4. Highlights / Shadows        ganho com mascara suave de luminosidade
    5. Saturation                  em luz linear
    6. Brightness                  exposicao em stops (EV), em luz linear

A cena chega codificada em sRGB (e pode passar de 1.0 com HDR). O passe
decodifica, ajusta e recodifica sem cortar no topo, entao o resolve HDR
continua recebendo os realces. Com tudo neutro o passe nem roda.

Controle do jogador: o desenvolvedor define o visual padrao e decide, por
controle, o que o jogador pode mexer (`PlayerControls`). Os ajustes do
jogador sao COMPOSTOS em cima do visual do jogo (deltas/multiplicadores
limitados), nunca substituem o estilo definido pelo desenvolvedor.
"""

import math

from . import glsl as glsl_mod

CALIB_NAME = "__color_calibration__"

# ---------------------------------------------------------------- limites
LEVEL_GAP = 0.02   # WhitePoint - BlackPoint nunca fica abaixo disso

# (min, max) aceitos do desenvolvedor
DEV_RANGES = {
    "black_point": (0.0, 0.9),
    "white_point": (0.1, 4.0),
    "brightness": (-4.0, 4.0),      # stops (EV)
    "contrast": (0.25, 3.0),
    "saturation": (0.0, 3.0),
    "highlights": (-1.0, 2.0),
    "shadows": (-1.0, 2.0),
    "gain": (0.0, 4.0),
    "offset": (-0.5, 0.5),
}

# (min, max) aceitos do jogador: delta (soma) ou multiplicador, conforme o controle
PLAYER_RANGES = {
    "brightness": (-1.5, 1.5),      # soma, em stops
    "contrast": (0.7, 1.4),         # multiplica
    "black_point": (-0.1, 0.1),     # soma
    "white_point": (-0.2, 0.2),     # soma
    "highlights": (-0.5, 0.5),      # soma
    "shadows": (-0.5, 0.5),         # soma
    "saturation": (0.5, 1.5),       # multiplica
    "rgb_gain": (0.8, 1.25),        # multiplica por canal
    "rgb_offset": (-0.05, 0.05),    # soma por canal
}

# controle (snake_case) -> nome publico no Lua
CONTROL_NAMES = {
    "brightness": "Brightness", "contrast": "Contrast",
    "black_point": "BlackPoint", "white_point": "WhitePoint",
    "highlights": "Highlights", "shadows": "Shadows",
    "rgb_gain": "RGBGain", "rgb_offset": "RGBOffset",
    "saturation": "Saturation",
}
CONTROLS = tuple(CONTROL_NAMES)
_CONTROL_LOOKUP = dict((v.lower(), k) for k, v in CONTROL_NAMES.items())
_CONTROL_LOOKUP.update((k, k) for k in CONTROLS)

# por padrao o jogador so recebe os controles basicos e seguros
DEFAULT_PLAYER_CONTROLS = {"brightness": True, "contrast": True, "saturation": True}

_SCALARS = ("black_point", "white_point", "brightness", "contrast",
            "saturation", "highlights", "shadows")
_CHANNELS = ("r", "g", "b")


def default_color_calibration_config():
    return {
        "enabled": False,
        "player_settings_enabled": False,
        "black_point": 0.0,
        "white_point": 1.0,
        "brightness": 0.0,
        "contrast": 1.0,
        "saturation": 1.0,
        "highlights": 0.0,
        "shadows": 0.0,
        "rgb_gain": [1.0, 1.0, 1.0],
        "rgb_offset": [0.0, 0.0, 0.0],
        "player_controls": dict((k, k in DEFAULT_PLAYER_CONTROLS) for k in CONTROLS),
    }


def default_player_settings():
    return {
        "brightness": 0.0, "contrast": 1.0, "black_point": 0.0, "white_point": 0.0,
        "highlights": 0.0, "shadows": 0.0, "saturation": 1.0,
        "rgb_gain": [1.0, 1.0, 1.0], "rgb_offset": [0.0, 0.0, 0.0],
    }


# ------------------------------------------------------------ validacao
def _num(value):
    if isinstance(value, bool):
        raise ValueError("booleano")
    val = float(value)
    if val != val or val in (float("inf"), float("-inf")):
        raise ValueError("nao finito")
    return val


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _flag(value):
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes", "sim")
    return bool(value)


def _channels(value, current):
    """Aceita {R=,G=,B=} (qualquer caixa), lista de 3 numeros ou um numero so.
    Canais ausentes mantem o valor atual. Levanta ValueError se invalido."""
    out = list(current)
    if isinstance(value, dict):
        keyed = dict((str(k).strip().lower(), v) for k, v in value.items())
        found = False
        for i, ch in enumerate(_CHANNELS):
            if ch in keyed:
                out[i] = _num(keyed[ch])
                found = True
            elif float(i + 1) in value or (i + 1) in value:
                out[i] = _num(value.get(float(i + 1), value.get(i + 1)))
                found = True
        if not found:
            raise ValueError("use R, G e B")
        return out
    if isinstance(value, (list, tuple)):
        if len(value) != 3:
            raise ValueError("use 3 valores (R, G, B)")
        return [_num(v) for v in value]
    return [_num(value)] * 3


def normalize_color_calibration(cfg, base=None, problems=None):
    """Valida `cfg` (snake_case) em cima de `base`. Valor invalido mantem o
    anterior; valor fora da faixa e ajustado. `problems` (lista) recebe o motivo."""
    out = dict(base) if base else default_color_calibration_config()
    out["rgb_gain"] = list(out["rgb_gain"])
    out["rgb_offset"] = list(out["rgb_offset"])
    out["player_controls"] = dict(out["player_controls"])
    if not isinstance(cfg, dict):
        return out

    def bad(key, value, why):
        if problems is not None:
            problems.append("valor invalido para %s: %r (%s)" % (key, value, why))

    for key in ("enabled", "player_settings_enabled"):
        if key in cfg:
            out[key] = _flag(cfg[key])
    for key in _SCALARS:
        if key in cfg:
            lo, hi = DEV_RANGES[key]
            try:
                val = _num(cfg[key])
            except (TypeError, ValueError):
                bad(key, cfg[key], "numero esperado")
                continue
            if not lo <= val <= hi:
                bad(key, cfg[key], "ajustado para %g..%g" % (lo, hi))
            out[key] = _clamp(val, lo, hi)
    for key, ranged in (("rgb_gain", "gain"), ("rgb_offset", "offset")):
        if key in cfg:
            lo, hi = DEV_RANGES[ranged]
            try:
                vals = _channels(cfg[key], out[key])
            except (TypeError, ValueError) as ex:
                bad(key, cfg[key], str(ex))
                continue
            if any(not lo <= v <= hi for v in vals):
                bad(key, cfg[key], "ajustado para %g..%g" % (lo, hi))
            out[key] = [_clamp(v, lo, hi) for v in vals]
    if "player_controls" in cfg:
        raw = cfg["player_controls"]
        if isinstance(raw, dict):
            controls = dict((k, False) for k in CONTROLS)   # tabela nova substitui tudo
            for name, flag in raw.items():
                canon = _CONTROL_LOOKUP.get(str(name).strip().lower())
                if canon is None:
                    bad("PlayerControls." + str(name), flag,
                        "controle desconhecido; use %s" % ", ".join(sorted(CONTROL_NAMES.values())))
                else:
                    controls[canon] = _flag(flag)
            out["player_controls"] = controls
        else:
            bad("player_controls", raw, "tabela esperada")
    # branco sempre acima do preto, com folga minima (evita divisao por zero)
    if out["white_point"] - out["black_point"] < LEVEL_GAP:
        fixed = min(DEV_RANGES["white_point"][1], out["black_point"] + LEVEL_GAP)
        if problems is not None:
            problems.append("WhitePoint (%g) precisa ser maior que BlackPoint (%g): ajustado para %g"
                            % (out["white_point"], out["black_point"], fixed))
        out["white_point"] = fixed
    return out


def normalize_player(values, base=None, problems=None, ranges=PLAYER_RANGES):
    """Valida ajustes do jogador (snake_case) limitando cada um a PLAYER_RANGES."""
    out = dict(base) if base else default_player_settings()
    out["rgb_gain"] = list(out["rgb_gain"])
    out["rgb_offset"] = list(out["rgb_offset"])
    if not isinstance(values, dict):
        return out

    def bad(key, value, why):
        if problems is not None:
            problems.append("valor invalido para Player.%s: %r (%s)" % (CONTROL_NAMES.get(key, key), value, why))

    for key, value in values.items():
        if key not in ranges:
            continue
        lo, hi = ranges[key]
        try:
            if key in ("rgb_gain", "rgb_offset"):
                vals = _channels(value, out[key])
            else:
                vals = [_num(value)]
        except (TypeError, ValueError) as ex:
            bad(key, value, str(ex))
            continue
        if any(not lo <= v <= hi for v in vals):
            bad(key, value, "limite do jogador: %g..%g" % (lo, hi))
        vals = [_clamp(v, lo, hi) for v in vals]
        out[key] = vals if key in ("rgb_gain", "rgb_offset") else vals[0]
    return out


# ------------------------------------------------- composicao e uniforms
def effective_settings(cfg, player=None):
    """Valores finais = visual do desenvolvedor + ajustes permitidos do jogador."""
    eff = {
        "black_point": cfg["black_point"], "white_point": cfg["white_point"],
        "brightness": cfg["brightness"], "contrast": cfg["contrast"],
        "saturation": cfg["saturation"], "highlights": cfg["highlights"],
        "shadows": cfg["shadows"],
        "gain": list(cfg["rgb_gain"]), "offset": list(cfg["rgb_offset"]),
    }
    if player and cfg["player_settings_enabled"]:
        allowed = cfg["player_controls"]
        for key in ("brightness", "black_point", "white_point", "highlights", "shadows"):
            if allowed.get(key):
                eff[key] += player[key]
        for key in ("contrast", "saturation"):
            if allowed.get(key):
                eff[key] *= player[key]
        if allowed.get("rgb_gain"):
            eff["gain"] = [g * p for g, p in zip(eff["gain"], player["rgb_gain"])]
        if allowed.get("rgb_offset"):
            eff["offset"] = [o + p for o, p in zip(eff["offset"], player["rgb_offset"])]
    for key in _SCALARS:
        lo, hi = DEV_RANGES[key]
        eff[key] = _clamp(eff[key], lo, hi)
    eff["gain"] = [_clamp(v, *DEV_RANGES["gain"]) for v in eff["gain"]]
    eff["offset"] = [_clamp(v, *DEV_RANGES["offset"]) for v in eff["offset"]]
    eff["white_point"] = max(eff["white_point"], eff["black_point"] + LEVEL_GAP)
    return eff


def is_identity(eff, eps=1e-6):
    return (abs(eff["black_point"]) < eps and abs(eff["white_point"] - 1.0) < eps
            and abs(eff["brightness"]) < eps and abs(eff["contrast"] - 1.0) < eps
            and abs(eff["saturation"] - 1.0) < eps and abs(eff["highlights"]) < eps
            and abs(eff["shadows"]) < eps
            and all(abs(g - 1.0) < eps for g in eff["gain"])
            and all(abs(o) < eps for o in eff["offset"]))


def uniforms_from(eff, clamp_output):
    return {
        "uBlackPoint": eff["black_point"],
        "uWhitePoint": eff["white_point"],
        "uBrightness": eff["brightness"],
        "uContrast": eff["contrast"],
        "uSaturation": eff["saturation"],
        "uHighlights": eff["highlights"],
        "uShadows": eff["shadows"],
        "uRGBGain": list(eff["gain"]),
        "uRGBOffset": list(eff["offset"]),
        "uClampOutput": 1.0 if clamp_output else 0.0,
    }


# ------------------------------------------------ referencia em Python
_LUMA = (0.2126, 0.7152, 0.0722)


def _srgb_to_linear(c):
    a = abs(c)
    v = a / 12.92 if a <= 0.04045 else ((a + 0.055) / 1.055) ** 2.4
    return math.copysign(v, c)


def _linear_to_srgb(c):
    c = max(c, 0.0)
    return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055


def _smoothstep(e0, e1, x):
    t = _clamp((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def calibrate_pixel(rgb, u):
    """Referencia em Python do shader (mesma ordem de passos). `rgb`: cena
    codificada em sRGB, pode passar de 1.0 com HDR."""
    e = [max(float(c), 0.0) for c in rgb[:3]]
    span = max(u["uWhitePoint"] - u["uBlackPoint"], 0.001)
    e = [max((c - u["uBlackPoint"]) / span, 0.0) for c in e]
    e = [max((c - 0.5) * u["uContrast"] + 0.5, 0.0) for c in e]
    lin = [_srgb_to_linear(c) for c in e]
    lin = [max(c * g + o, 0.0) for c, g, o in zip(lin, u["uRGBGain"], u["uRGBOffset"])]
    y = _linear_to_srgb(sum(c * w for c, w in zip(lin, _LUMA)))
    hi = _smoothstep(0.45, 0.90, y)
    sh = 1.0 - _smoothstep(0.05, 0.40, y)
    k = max(1.0 + u["uHighlights"] * hi + u["uShadows"] * sh, 0.0)
    lin = [c * k for c in lin]
    lum = sum(c * w for c, w in zip(lin, _LUMA))
    lin = [max(lum + (c - lum) * u["uSaturation"], 0.0) for c in lin]
    gain = 2.0 ** u["uBrightness"]
    out = [_linear_to_srgb(c * gain) for c in lin]
    if u["uClampOutput"] > 0.5:
        out = [min(c, 1.0) for c in out]
    return tuple(out)


# ---------------------------------------------------------------- shader
CALIB_FRAGMENT = """
uniform float uBlackPoint;
uniform float uWhitePoint;
uniform float uBrightness;
uniform float uContrast;
uniform float uSaturation;
uniform float uHighlights;
uniform float uShadows;
uniform vec3 uRGBGain;
uniform vec3 uRGBOffset;
uniform float uClampOutput;

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);

vec3 srgbToLinear(vec3 c)
{
    vec3 a = abs(c);
    vec3 lo = a / 12.92;
    vec3 hi = pow((a + 0.055) / 1.055, vec3(2.4));
    return sign(c) * mix(hi, lo, step(a, vec3(0.04045)));
}

// sem corte no topo: com HDR os realces acima de 1.0 seguem pro resolve
vec3 linearToSrgbExt(vec3 c)
{
    c = max(c, vec3(0.0));
    vec3 lo = c * 12.92;
    vec3 hi = 1.055 * pow(max(c, vec3(0.0031308)), vec3(1.0 / 2.4)) - 0.055;
    return mix(hi, lo, step(c, vec3(0.0031308)));
}

void main(void)
{
    vec4 src = texture2D(texture0, tex_coord0);
    vec3 e = max(src.rgb, vec3(0.0));

    // 1) niveis e 2) contraste, em valor codificado
    e = max((e - vec3(uBlackPoint)) / max(uWhitePoint - uBlackPoint, 0.001), vec3(0.0));
    e = max((e - 0.5) * uContrast + 0.5, vec3(0.0));

    // 3) RGB em luz linear
    vec3 c = srgbToLinear(e);
    c = max(c * uRGBGain + uRGBOffset, vec3(0.0));

    // 4) realces / sombras: ganho com mascara suave (sem faixas artificiais)
    float y = linearToSrgbExt(vec3(dot(c, LUMA))).x;
    float hi = smoothstep(0.45, 0.90, y);
    float sh = 1.0 - smoothstep(0.05, 0.40, y);
    c *= max(1.0 + uHighlights * hi + uShadows * sh, 0.0);

    // 5) saturacao
    float lum = dot(c, LUMA);
    c = max(mix(vec3(lum), c, uSaturation), vec3(0.0));

    // 6) brilho em stops
    c *= exp2(uBrightness);

    vec3 o = linearToSrgbExt(c);
    if (uClampOutput > 0.5)
        o = min(o, vec3(1.0));
    gl_FragColor = vec4(o, src.a);
}
"""

glsl_mod.SHADERS.register(CALIB_NAME, CALIB_FRAGMENT)


# ----------------------------------------------------------------- estado
class ColorCalibrationState(object):
    """Estado de calibracao de um Runtime: junta visual do jogo + ajustes do
    jogador e entrega ao Stage o passe com seus uniforms."""

    def __init__(self, runtime):
        self.rt = runtime
        self.player = default_player_settings()

    @property
    def cfg(self):
        return self.rt.render["color_calibration"]

    # ---- composicao
    def effective(self):
        return effective_settings(self.cfg, self.player)

    def is_active(self):
        return bool(self.cfg["enabled"]) and not is_identity(self.effective())

    def uniforms(self):
        # com HDR/Preview o resolve vem depois: nao corta os realces aqui
        clamp = self.rt.hdr.mode == "off"
        return uniforms_from(self.effective(), clamp)

    def plan_entry(self):
        if not self.is_active():
            return None
        return (CALIB_NAME, self.uniforms())

    # ---- jogador
    def player_enabled(self):
        return bool(self.cfg["enabled"] and self.cfg["player_settings_enabled"])

    def can_adjust(self, control):
        canon = _CONTROL_LOOKUP.get(str(control).strip().lower())
        return bool(canon and self.player_enabled() and self.cfg["player_controls"].get(canon))

    def allowed_controls(self):
        return [CONTROL_NAMES[k] for k in CONTROLS if self.can_adjust(k)]

    def set_player(self, control, value):
        """Define um ajuste do jogador. Respeita PlayerSettingsEnabled e
        PlayerControls; valor fora do limite e ajustado. Devolve True se aplicou."""
        canon = _CONTROL_LOOKUP.get(str(control).strip().lower())
        if canon is None:
            self.rt.log("[ColorCalibration] controle desconhecido: Player.%s (use %s)"
                        % (control, ", ".join(sorted(CONTROL_NAMES.values()))))
            return False
        if not self.player_enabled():
            self.rt.log("[ColorCalibration] ajuste do jogador desativado "
                        "(Enabled e PlayerSettingsEnabled precisam ser true): Player.%s ignorado"
                        % CONTROL_NAMES[canon])
            return False
        if not self.cfg["player_controls"].get(canon):
            self.rt.log("[ColorCalibration] o jogo nao permite o jogador mexer em %s" % CONTROL_NAMES[canon])
            return False
        problems = []
        self.player = normalize_player({canon: value}, self.player, problems)
        for why in problems:
            self.rt.log("[ColorCalibration] " + why)
        return True

    def reset_player(self):
        self.player = default_player_settings()

    def player_values(self):
        """Ajustes do jogador permitidos agora (para o jogo salvar em SaveData)."""
        out = {}
        for key in CONTROLS:
            if self.can_adjust(key):
                out[CONTROL_NAMES[key]] = self.player[key]
        return out

    # ---- Lua
    def status_dict(self):
        eff = self.effective()
        return {"Enabled": bool(self.cfg["enabled"]), "Active": self.is_active(),
                "PlayerSettingsEnabled": bool(self.cfg["player_settings_enabled"]),
                "Output": "Clamp" if self.rt.hdr.mode == "off" else "HDR",
                "BlackPoint": eff["black_point"], "WhitePoint": eff["white_point"],
                "Brightness": eff["brightness"], "Contrast": eff["contrast"],
                "Saturation": eff["saturation"], "Highlights": eff["highlights"],
                "Shadows": eff["shadows"],
                "RGBGain": dict(zip("RGB", eff["gain"])),
                "RGBOffset": dict(zip("RGB", eff["offset"]))}


# --------------------------------------------------------------- API Lua
def _lua_table(values):
    from .lua import LuaTable
    t = LuaTable()
    for k, v in values.items():
        if isinstance(v, dict):
            v = _lua_table(v)
        t.set(k, v)
    return t


def _to_py(value):
    from .lua import LuaTable
    if isinstance(value, LuaTable):
        out = {}
        for k, v in value.items():
            out[int(k) if isinstance(k, float) and k == int(k) else k] = _to_py(v)
        return out
    return value


_PROPS = {
    "Enabled": "enabled", "PlayerSettingsEnabled": "player_settings_enabled",
    "BlackPoint": "black_point", "WhitePoint": "white_point",
    "Brightness": "brightness", "Contrast": "contrast", "Saturation": "saturation",
    "Highlights": "highlights", "Shadows": "shadows",
}


class _ChannelAPI(object):
    """`...RGB.Gain` / `...RGB.Offset`: leitura/escrita de R, G e B."""

    def __init__(self, getter, setter):
        self._get = getter
        self._set = setter

    def lua_index(self, key):
        k = str(key).upper()
        if k in ("R", "G", "B"):
            return self._get()["RGB".index(k)]
        return None

    def lua_newindex(self, key, value):
        k = str(key).upper()
        if k in ("R", "G", "B"):
            self._set({k: value})
        else:
            self._set({})


class _RGBAPI(object):
    def __init__(self, getter, setter):
        self._getter = getter
        self._setter = setter

    def lua_index(self, key):
        k = str(key)
        if k in ("Gain", "Offset"):
            return _ChannelAPI(lambda: self._getter(k), lambda v: self._setter(k, v))
        return None

    def lua_newindex(self, key, value):
        k = str(key)
        if k in ("Gain", "Offset"):
            self._setter(k, _to_py(value))
        else:
            self._setter("?" + k, value)


class _PlayerControlsAPI(object):
    def __init__(self, runtime):
        self.rt = runtime

    def lua_index(self, key):
        canon = _CONTROL_LOOKUP.get(str(key).strip().lower())
        if canon is None:
            return None
        return bool(self.rt.render["color_calibration"]["player_controls"][canon])

    def lua_newindex(self, key, value):
        controls = dict(self.rt.render["color_calibration"]["player_controls"])
        canon = _CONTROL_LOOKUP.get(str(key).strip().lower())
        controls[canon or str(key)] = value
        self.rt.set_color_calibration("player_controls", controls)


class _PlayerAPI(object):
    """`Graphics.ColorCalibration.Player`: ajustes do jogador (limitados e
    condicionados a PlayerSettingsEnabled/PlayerControls)."""

    def __init__(self, runtime):
        self.rt = runtime
        self.rgb = _RGBAPI(self._rgb_get, self._rgb_set)

    def _rgb_get(self, which):
        return list(self.rt.colorcal.player["rgb_gain" if which == "Gain" else "rgb_offset"])

    def _rgb_set(self, which, value):
        if which.startswith("?"):
            self.rt.log("[ColorCalibration] propriedade desconhecida: Player.RGB.%s (use Gain, Offset)" % which[1:])
            return
        if not isinstance(value, dict):
            value = {} if value is None else value
        self.rt.colorcal.set_player("RGBGain" if which == "Gain" else "RGBOffset", value)

    def lua_index(self, key):
        k = str(key)
        canon = _CONTROL_LOOKUP.get(k.strip().lower())
        if canon in self.rt.colorcal.player and canon not in ("rgb_gain", "rgb_offset"):
            return self.rt.colorcal.player[canon]
        if k == "RGB":
            return self.rgb
        return getattr(self, "m_" + k, None)

    def lua_newindex(self, key, value):
        k = str(key)
        if k == "RGB":
            self.rt.log("[ColorCalibration] use Player.RGB.Gain / Player.RGB.Offset")
            return
        self.rt.colorcal.set_player(k, _to_py(value))

    def m_Reset(self, *_a):
        self.rt.colorcal.reset_player()
        return True

    def m_CanAdjust(self, *a):
        # chamada com ':' recebe o objeto primeiro
        name = a[-1] if a else None
        return self.rt.colorcal.can_adjust(name)

    def m_GetControls(self, *_a):
        from .lua import LuaTable
        return LuaTable(self.rt.colorcal.allowed_controls())

    def m_Get(self, *_a):
        out = {}
        for key, value in self.rt.colorcal.player_values().items():
            out[key] = _lua_table(dict(zip("RGB", value))) if isinstance(value, list) else value
        return _lua_table(out)

    def m_Set(self, *a):
        """Restaura ajustes salvos (ex.: lidos de SaveData). Ignora o que nao e permitido."""
        data = _to_py(a[-1]) if a else None
        if not isinstance(data, dict):
            return False
        for key, value in data.items():
            self.rt.colorcal.set_player(key, value)
        return True


class ColorCalibrationAPI(object):
    """`Graphics.ColorCalibration` no Lua."""

    def __init__(self, runtime):
        self.rt = runtime
        self.player = _PlayerAPI(runtime)
        self.controls = _PlayerControlsAPI(runtime)
        self.rgb = _RGBAPI(self._rgb_get, self._rgb_set)

    def _rgb_get(self, which):
        return list(self.rt.render["color_calibration"]["rgb_gain" if which == "Gain" else "rgb_offset"])

    def _rgb_set(self, which, value):
        if which.startswith("?"):
            self.rt.log("[ColorCalibration] propriedade desconhecida: RGB.%s (use Gain, Offset)" % which[1:])
            return
        self.rt.set_color_calibration("rgb_gain" if which == "Gain" else "rgb_offset", value)

    def lua_index(self, key):
        k = str(key)
        if k in _PROPS:
            return self.rt.render["color_calibration"][_PROPS[k]]
        if k == "RGB":
            return self.rgb
        if k == "PlayerControls":
            return self.controls
        if k == "Player":
            return self.player
        if k == "Active":
            return self.rt.colorcal.is_active()
        return getattr(self, "m_" + k, None)

    def lua_newindex(self, key, value):
        from .lua import LuaError
        k = str(key)
        if k in _PROPS:
            self.rt.set_color_calibration(_PROPS[k], value)
        elif k == "PlayerControls":
            self.rt.set_color_calibration("player_controls", _to_py(value))
        elif k == "RGB":
            self.rt.log("[ColorCalibration] use RGB.Gain = {R=,G=,B=} ou RGB.Offset = {R=,G=,B=}")
        elif k in ("Active", "Player"):
            raise LuaError("Graphics.ColorCalibration.%s e somente leitura" % k)
        else:
            self.rt.log("[ColorCalibration] propriedade desconhecida: Graphics.ColorCalibration.%s (use %s)"
                        % (k, ", ".join(sorted(list(_PROPS) + ["RGB", "PlayerControls"]))))

    def m_IsActive(self, *_a):
        return self.rt.colorcal.is_active()

    def m_GetStatus(self, *_a):
        return _lua_table(self.rt.colorcal.status_dict())

    def m_Reset(self, *_a):
        """Volta o visual do desenvolvedor ao neutro (mantem permissoes)."""
        base = default_color_calibration_config()
        keep = dict((k, self.rt.render["color_calibration"][k])
                    for k in ("enabled", "player_settings_enabled", "player_controls"))
        base.update(keep)
        self.rt.render["color_calibration"] = base
        return True
