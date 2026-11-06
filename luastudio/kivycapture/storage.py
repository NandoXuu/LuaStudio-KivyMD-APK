r"""Armazenamento multiplataforma: Windows, Android, Linux/macOS.

- Windows : Imagens\KivyCapture / Vídeos\KivyCapture (respeita OneDrive), ou
            qualquer caminho (C:\..., D:\..., \\servidor\pasta, ~, %VARS%).
- Android : grava na pasta do app e publica na galeria
            (Pictures/KivyCapture, Movies/KivyCapture) via MediaStore.
- Qualquer: caminho absoluto, relativo, com ~ ou variáveis de ambiente.
"""
import difflib
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

APP_SUBDIR = "KivyCapture"
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".webp": "image/webp", ".avi": "video/x-msvideo"}


def _log(msg):
    try:
        from kivy.logger import Logger
        Logger.info("KivyCapture: " + msg)
    except Exception:
        print("[KivyCapture]", msg)


def is_android():
    if "ANDROID_ARGUMENT" in os.environ:
        return True
    if "ANDROID_ROOT" in os.environ and "ANDROID_DATA" in os.environ:
        return True   # Pydroid 3, Termux etc.
    try:
        from kivy.utils import platform
        return platform == "android"
    except Exception:
        return False


def is_windows():
    return sys.platform.startswith("win")


# ------------------------------------------------------------ Android
def _android_context():
    """Activity atual (p4a/buildozer, Pydroid 3 quando disponível)."""
    try:
        from android import mActivity  # python-for-android recente
        if mActivity is not None:
            return mActivity
    except Exception:
        pass
    from jnius import autoclass
    last = None
    for cls in ("org.kivy.android.PythonActivity", "org.renpy.android.PythonActivity"):
        try:
            act = autoclass(cls).mActivity
            if act is not None:
                return act
        except Exception as e:
            last = e
    raise RuntimeError("sem Activity Android acessível: %r" % last)


def android_api():
    from jnius import autoclass
    return int(autoclass("android.os.Build$VERSION").SDK_INT)


def request_permissions():
    """Só necessário no Android 9 ou anterior (API < 29)."""
    if not is_android():
        return
    try:
        if android_api() < 29:
            from android.permissions import request_permissions as rp, Permission
            rp([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])
    except Exception as e:
        _log("não foi possível pedir permissões: %r" % e)


def _android_private_dir():
    try:
        d = _android_context().getExternalFilesDir(None)
        if d is not None:
            return Path(d.getAbsolutePath()) / "captures"
    except Exception:
        pass
    try:
        from kivy.app import App
        return Path(App.get_running_app().user_data_dir) / "captures"
    except Exception:
        return Path(tempfile.gettempdir()) / APP_SUBDIR


def _publish_android(path, mime, subdir, delete_source):
    from jnius import autoclass
    ctx = _android_context()
    path = Path(path)
    is_video = mime.startswith("video")
    Env = autoclass("android.os.Environment")
    base = Env.DIRECTORY_MOVIES if is_video else Env.DIRECTORY_PICTURES
    if android_api() >= 29:
        MediaStore = autoclass("android.provider.MediaStore")
        CV = autoclass("android.content.ContentValues")
        cv = CV()
        cv.put("_display_name", path.name)
        cv.put("mime_type", mime)
        cv.put("relative_path", "%s/%s" % (base, subdir))
        coll = (MediaStore.Video.Media.EXTERNAL_CONTENT_URI if is_video
                else MediaStore.Images.Media.EXTERNAL_CONTENT_URI)
        resolver = ctx.getContentResolver()
        uri = resolver.insert(coll, cv)
        if uri is None:
            raise OSError("MediaStore recusou o arquivo")
        out = resolver.openOutputStream(uri)
        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
        finally:
            out.close()
        shown = "%s/%s/%s" % (base, subdir, path.name)
    else:
        pub = Path(Env.getExternalStoragePublicDirectory(base).getAbsolutePath()) / subdir
        pub.mkdir(parents=True, exist_ok=True)
        dest = pub / path.name
        shutil.copy2(path, dest)
        autoclass("android.media.MediaScannerConnection").scanFile(
            ctx, [str(dest)], None, None)
        shown = str(dest)
    if delete_source:
        try:
            path.unlink()
        except OSError:
            pass
    return shown



# ------------------------------------------------------------ caminhos livres
ANDROID_PRIMARY = "/storage/emulated/0"
_ANDROID_ALIASES = ("/storage/emulated/0", "/storage/self/primary", "/sdcard",
                    "/mnt/sdcard", "/storage/emulated/legacy")


def _fix_components(root, rel_parts):
    """Corrige maiúsculas/minúsculas e pequenos erros de digitação do 1º nível
    (ex.: 'Dowloads' -> 'Download') comparando com o que existe de verdade.
    Pastas que não existem continuam como o usuário escreveu (serão criadas)."""
    cur = Path(root)
    out = []
    for i, part in enumerate(rel_parts):
        nxt = cur / part
        if not os.path.exists(str(nxt)) and os.path.isdir(str(cur)):
            try:
                names = [n for n in os.listdir(cur)]
            except OSError:
                names = []
            match = next((n for n in names if n.lower() == part.lower()), None)
            if match is None and i == 0:
                dirs = {n.lower(): n for n in names if os.path.isdir(os.path.join(str(cur), n))}
                close = difflib.get_close_matches(part.lower(), list(dirs), n=1, cutoff=0.8)
                if close:
                    match = dirs[close[0]]
                    _log("pasta '%s' não existe; usando '%s'" % (part, match))
            if match:
                part = match
        out.append(part)
        cur = cur / part
    return Path(root).joinpath(*out) if out else Path(root)


def normalize_android_path(p):
    """/storage/Emulated/0/Dowloads/pictures -> /storage/emulated/0/Download/pictures
    (Android diferencia maiúsculas de minúsculas). Nunca levanta exceção."""
    try:
        return _normalize_android_path(p)
    except Exception as e:
        _log("não foi possível normalizar %s (%r); usando como foi escrito" % (p, e))
        return Path(str(p))


def _normalize_android_path(p):
    s = str(p).replace("\\", "/")
    low = s.lower()
    for alias in _ANDROID_ALIASES:
        if low == alias or low.startswith(alias + "/"):
            rel = [x for x in s[len(alias):].split("/") if x]
            return _fix_components(ANDROID_PRIMARY, rel)
    return Path(s)


def has_all_files_access():
    """True/False no Android 11+; None se não der para saber."""
    if not is_android():
        return True
    try:
        from jnius import autoclass
        return bool(autoclass("android.os.Environment").isExternalStorageManager())
    except Exception:
        return None


def request_all_files_access():
    """Abre a tela do Android 'Permitir gerenciar todos os arquivos' para este app.
    Necessário para gravar em /storage/emulated/0/... em qualquer pasta."""
    if not is_android():
        return False
    try:
        from jnius import autoclass
        ctx = _android_context()
        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")
        it = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                    Uri.parse("package:" + ctx.getPackageName()))
        ctx.startActivity(it)
        return True
    except Exception as e:
        _log("abra manualmente: Configurações > Apps > (seu app/Pydroid 3) > "
             "Permissões > Arquivos > 'Permitir gerenciar todos os arquivos' (%r)" % e)
        return False


def scan_media(path):
    """Faz a galeria enxergar um arquivo salvo em pasta livre (best effort)."""
    if not is_android():
        return
    try:
        from jnius import autoclass
        autoclass("android.media.MediaScannerConnection").scanFile(
            _android_context(), [str(path)], None, None)
    except Exception:
        pass


def _probe(folder):
    """Teste real de escrita (os.access não é confiável no Android)."""
    folder.mkdir(parents=True, exist_ok=True)
    t = folder / (".kc_probe_%d" % os.getpid())
    with open(t, "wb") as f:
        f.write(b"x")
    t.unlink()


def _permission_hint(folder):
    if is_android():
        return ("Sem permissão para gravar em '%s'. No Android 11+ ative "
                "'Permitir gerenciar todos os arquivos' para o app (Pydroid 3: "
                "Configurações > Apps > Pydroid 3 > Permissões > Arquivos), ou "
                "chame storage.request_all_files_access()." % folder)
    return "Sem permissão para gravar em '%s'." % folder

# ------------------------------------------------------------ Windows/outros
def _windows_known(csidl):
    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
        return Path(buf.value)
    raise OSError("SHGetFolderPathW falhou")


def default_dir(kind="image"):
    """Pasta padrão visível para o usuário. kind: 'image' ou 'video'."""
    if is_android():
        try:
            _android_context()
            return _android_private_dir()   # será publicada na galeria
        except Exception:
            return Path(ANDROID_PRIMARY) / ("Movies" if kind == "video" else "Pictures") / APP_SUBDIR
    name = "Videos" if kind == "video" else "Pictures"
    if is_windows():
        try:
            return _windows_known(0x0E if kind == "video" else 0x27) / APP_SUBDIR
        except Exception:
            pass
    return Path.home() / name / APP_SUBDIR


def fallback_dir():
    return _android_private_dir() if is_android() else Path(tempfile.gettempdir()) / APP_SUBDIR


def expand(p):
    p = Path(os.path.expandvars(os.path.expanduser(str(p))))
    return normalize_android_path(p) if is_android() else p


def resolve_path(name, base_dir, ext, strict=False):
    """Monta o caminho final a partir de nome/pasta/caminho completo.
    - None            -> base_dir/AAAAmmdd_HHMMSS<ext>
    - 'foto.png'      -> base_dir/foto.png
    - 'D:\\x\\a.png'  -> caminho absoluto (qualquer disco/pasta)
    - '/storage/emulated/0/Download/x/' -> pasta + nome automático
    Cria as pastas e testa a escrita de verdade.
    strict=True : se não puder gravar, levanta PermissionError (sem desvio).
    strict=False: cai para a pasta do app."""
    auto = time.strftime("%Y%m%d_%H%M%S") + ext
    if name is None:
        p = expand(base_dir) / auto
    else:
        s = str(name)
        p = expand(s)
        if s.endswith(("/", "\\")) or os.path.isdir(str(p)):
            p = p / auto
        elif not p.is_absolute():
            p = expand(base_dir) / p
        if not p.suffix:
            p = p.with_name(p.name + ext)
    try:
        _probe(p.parent)
        return p
    except OSError as e:
        if strict:
            raise PermissionError("%s (%r)" % (_permission_hint(p.parent), e))
        fb = fallback_dir()
        fb.mkdir(parents=True, exist_ok=True)
        _log("sem acesso a %s (%r); usando %s" % (p.parent, e, fb))
        return fb / p.name


def publish(path, gallery=True, delete_source=True):
    """No Android, copia para a galeria (MediaStore). Nas outras plataformas
    não faz nada. Retorna o local onde o arquivo ficou."""
    if gallery and is_android():
        mime = _MIME.get(Path(path).suffix.lower(), "application/octet-stream")
        try:
            return _publish_android(path, mime, APP_SUBDIR, delete_source)
        except Exception as e:
            _log("falha ao publicar na galeria (%r); arquivo mantido em %s" % (e, path))
    return str(path)


def export(src, dest=None, kind="image", gallery=False):
    """Copia um arquivo já salvo para qualquer pasta/disco."""
    src = Path(src)
    dest_path = resolve_path(dest, default_dir(kind), src.suffix)
    shutil.copy2(src, dest_path)
    return publish(dest_path, gallery=gallery, delete_source=False) if gallery else str(dest_path)


def open_folder(path):
    """Abre a pasta no explorador (Windows/macOS/Linux). No Android não faz nada."""
    folder = Path(path)
    folder = folder if os.path.isdir(str(folder)) else folder.parent
    try:
        if is_windows():
            os.startfile(str(folder))
        elif sys.platform == "darwin":
            os.system('open "%s"' % folder)
        elif not is_android():
            os.system('xdg-open "%s"' % folder)
    except Exception as e:
        _log("não consegui abrir a pasta: %r" % e)


def pick_folder(initial=None):
    """Seletor de pasta (desktop, via tkinter da biblioteca padrão)."""
    if is_android():
        return None
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk(); root.withdraw()
        root.attributes("-topmost", True)
        d = filedialog.askdirectory(initialdir=str(initial) if initial else None)
        root.destroy()
        return d or None
    except Exception:
        return None
