import json
import os

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "editor_prefs.json")

DEFAULTS = {
    "font_size": 15,
    "indent_guides": True,
    "autocomplete_enabled": True,
    "auto_close_pairs": True,
    "indent_width": 2,
    "word_wrap": True,
    "minimap": False,
    "autosave_seconds": 30,
    "theme_name": "dark",
    "accent_color": "#4aa3ff",
    "ui_scale": 1.0,
    "language": "pt-BR",
    "left_handed": False,
    "render_scale": 1.0,
    "show_fps": False,
    "indent_with_tabs": False,
    "show_whitespace": False,
    "minimap": False,
    "symbol_bar_position": "bottom",
    "symbol_bar_items": ["Tab", "←", "--", "=", "{}", "()", "\"\"", "end"],
    "theme_name": "dark",
    "high_contrast": False,
    "ui_button_scale": 1.0,
    "console_height": 220,
    "console_filters": ["log", "warning", "error"],
    "clear_console_on_play": True,
    "auto_reload_on_save": False,
    "fixed_aspect_ratio": "auto",
    "orientation": "auto",
    "vsync": True,
    "low_battery_fps": 30,
    "shader_default": "lambert",
    "max_lights": 8,
    "shadow_quality": "medium",
    "draw_distance": 500,
    "fog_enabled": True,
    "shadows_enabled": True,
    "debug_wireframe": False,
    "debug_colliders": False,
    "debug_normals": False,
    "debug_axes": False,
    "profiler_enabled": False,
    "plugins_enabled": True,
}

_data = None


def _load():
    global _data
    if _data is None:
        _data = dict(DEFAULTS)
        try:
            with open(_PATH, encoding="utf-8") as fh:
                saved = json.load(fh)
            if isinstance(saved, dict):
                _data.update(saved)
        except Exception:
            pass
    return _data


def get(key):
    return _load().get(key, DEFAULTS.get(key))


def set(key, value):
    _load()[key] = value
    try:
        with open(_PATH, "w", encoding="utf-8") as fh:
            json.dump(_data, fh)
    except Exception:
        pass

def export_preferences(path):
    """Exporta preferências globais para JSON portátil."""
    import json
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_load(), fh, indent=2, ensure_ascii=False)
    return path

def import_preferences(path):
    """Importa preferências conhecidas, preservando defaults e ignorando lixo."""
    import json
    with open(path, "r", encoding="utf-8") as fh:
        values = json.load(fh)
    if not isinstance(values, dict):
        raise ValueError("O arquivo de preferências precisa ser um objeto JSON.")
    allowed = set(DEFAULTS)
    accepted = {k: v for k, v in values.items() if k in allowed}
    _load().update(accepted)
    with open(_PATH, "w", encoding="utf-8") as fh:
        json.dump(_data, fh, indent=2, ensure_ascii=False)
    return len(accepted)
