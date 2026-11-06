import os

from kivy.core.text import LabelBase
from kivy.uix.label import Label

try:
    from kivymd.icon_definitions import md_icons as _MD_ICONS
except Exception:
    _MD_ICONS = None

FALLBACK = "help-circle-outline"
FONT_NAME = "LuaStudioMDI"

LEGACY_TO_MD = {
    "add": "plus",
    "back": "arrow-left",
    "brush": "brush",
    "bucket": "format-color-fill",
    "check": "check",
    "clear": "close-circle-outline",
    "close": "close",
    "code": "code-braces",
    "delete": "delete-outline",
    "download": "download-outline",
    "edit": "pencil-outline",
    "eraser": "eraser",
    "file": "file-outline",
    "fit": "fit-to-screen-outline",
    "folder": "folder-outline",
    "home": "home-outline",
    "image": "image-outline",
    "import": "file-import-outline",
    "info": "information-outline",
    "lock": "lock-outline",
    "map": "map-outline",
    "new_file": "file-plus-outline",
    "output": "export-variant",
    "pages": "layers-outline",
    "pan": "cursor-move",
    "play": "play",
    "plugin": "puzzle-outline",
    "refresh": "refresh",
    "save": "content-save-outline",
    "screen": "cellphone",
    "search": "magnify",
    "settings": "cog-outline",
    "star": "star-outline",
    "stop": "stop",
    "system": "application-cog-outline",
    "target": "target",
    "terminal": "console",
    "undo": "undo",
    "upload": "upload-outline",
    "warning": "alert-outline",
    "zoom_in": "magnify-plus-outline",
    "zoom_out": "magnify-minus-outline",
}


def _find_font():
    try:
        import kivymd
    except Exception:
        return None
    root = os.path.dirname(os.path.abspath(kivymd.__file__))
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            low = f.lower().replace("-", "").replace("_", "").replace(" ", "")
            if low.endswith(".ttf") and "materialdesign" in low:
                return os.path.join(dirpath, f)
    return None


_FONT_OK = False
try:
    _font_path = _find_font()
    if _font_path:
        LabelBase.register(name=FONT_NAME, fn_regular=_font_path)
        _FONT_OK = True
except Exception:
    _FONT_OK = False


def exists(name):
    return bool(name) and (_MD_ICONS is None or name in _MD_ICONS)


def resolve(name, fallback=FALLBACK):
    if not name:
        return None
    md = LEGACY_TO_MD.get(name, name)
    if exists(md):
        return md
    if exists(fallback):
        return fallback
    return None


def _glyph_char(name):
    if not _MD_ICONS or not name:
        return None
    return _MD_ICONS.get(name)


def make_icon(name, px, color=(1, 1, 1, 1)):
    name = resolve(name)
    if not name:
        return None
    ch = _glyph_char(name) if _FONT_OK else None
    if ch:
        lab = Label(text=ch, font_name=FONT_NAME, font_size=px * 0.9,
                    color=color, halign="center", valign="middle",
                    size_hint=(None, None), size=(px, px))
        lab.bind(size=lambda w, v: setattr(w, "text_size", v))
        return lab
    try:
        from kivymd.uix.label import MDIcon
        icon = MDIcon(icon=name, halign="center", valign="middle",
                      font_size=px, size_hint=(None, None), size=(px, px))
        icon.bind(size=lambda w, v: setattr(w, "text_size", v))
        return icon
    except Exception:
        return None
