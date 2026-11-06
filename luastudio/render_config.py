# -*- coding: utf-8 -*-
from . import hdr
from . import colorcal

FPS_CHOICES = (30, 45, 60, 90, 120)
FILTER_CHOICES = ("linear", "nearest")
FPS_MIN = 10
FPS_MAX = 240
DEFAULT_FPS = 45

_FILTER_ALIASES = {
    "linear": "linear", "bilinear": "linear", "smooth": "linear",
    "nearest": "nearest", "point": "nearest", "pixel": "nearest",
}


def default_render_config():
    return {"fps_limit": DEFAULT_FPS, "texture_filter": "linear",
            "show_fps": False, "background": "", "render_scale": 1.0,
            "max_lights": 8, "shadow_quality": "medium", "draw_distance": 500.0,
            "fog_enabled": True, "shadows_enabled": True,
            "shader_default": "lambert", "screen_fit": "keep_aspect",
            "orientation": "auto", "fixed_aspect_ratio": None,
            "vsync": True, "low_battery_fps": 30,
            "wireframe": False, "debug_colliders": False,
            "debug_normals": False, "debug_axes": False,
            "hdr": hdr.default_hdr_config(),
            "color_calibration": colorcal.default_color_calibration_config()}


def normalize_fps(value, fallback=DEFAULT_FPS):
    try:
        fps = int(round(float(value)))
    except (TypeError, ValueError):
        return fallback
    return max(FPS_MIN, min(FPS_MAX, fps))


def normalize_filter(value, fallback="linear"):
    return _FILTER_ALIASES.get(str(value or "").strip().lower(), fallback)


def normalize_background(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.startswith("#"):
        text = "#" + text
    digits = text[1:]
    if len(digits) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in digits):
        return "#" + digits.lower()
    return ""


def normalize(cfg, base=None):
    out = dict(base) if base else default_render_config()
    if isinstance(cfg, dict):
        if "fps_limit" in cfg:
            out["fps_limit"] = normalize_fps(cfg["fps_limit"], out["fps_limit"])
        if "texture_filter" in cfg:
            out["texture_filter"] = normalize_filter(cfg["texture_filter"], out["texture_filter"])
        if "show_fps" in cfg:
            out["show_fps"] = bool(cfg["show_fps"])
        if "background" in cfg:
            out["background"] = normalize_background(cfg["background"])
        if "render_scale" in cfg:
            try: out["render_scale"] = max(0.25, min(1.0, float(cfg["render_scale"])))
            except (TypeError, ValueError): pass
        if "max_lights" in cfg:
            try: out["max_lights"] = max(0, min(128, int(cfg["max_lights"])))
            except (TypeError, ValueError): pass
        if "draw_distance" in cfg:
            try: out["draw_distance"] = max(1.0, min(100000.0, float(cfg["draw_distance"])))
            except (TypeError, ValueError): pass
        for key in ("fog_enabled", "shadows_enabled", "vsync", "wireframe", "debug_colliders", "debug_normals", "debug_axes"):
            if key in cfg: out[key] = bool(cfg[key])
        if "shadow_quality" in cfg and cfg["shadow_quality"] in ("off", "low", "medium", "high"):
            out["shadow_quality"] = cfg["shadow_quality"]
        if "shader_default" in cfg and cfg["shader_default"] in ("lambert", "toon", "pbr-lite"):
            out["shader_default"] = cfg["shader_default"]
        if "screen_fit" in cfg and cfg["screen_fit"] in ("stretch", "keep_aspect", "pixel_perfect"):
            out["screen_fit"] = cfg["screen_fit"]
        if "orientation" in cfg and cfg["orientation"] in ("auto", "portrait", "landscape"):
            out["orientation"] = cfg["orientation"]
        if "fixed_aspect_ratio" in cfg:
            val = cfg["fixed_aspect_ratio"]
            try: out["fixed_aspect_ratio"] = max(0.1, min(10.0, float(val))) if val else None
            except (TypeError, ValueError): pass
        if "low_battery_fps" in cfg:
            out["low_battery_fps"] = normalize_fps(cfg["low_battery_fps"])
        if "hdr" in cfg:
            out["hdr"] = hdr.normalize_hdr(cfg["hdr"], out.get("hdr"))
        if "color_calibration" in cfg:
            out["color_calibration"] = colorcal.normalize_color_calibration(
                cfg["color_calibration"], out.get("color_calibration"))
    return out


def tick_interval(fps):
    return 1.0 / normalize_fps(fps)
