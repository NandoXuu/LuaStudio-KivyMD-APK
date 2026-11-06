"""KivyCapture - captura de tela e gravação de vídeo para Kivy.
Sem OpenCV, sem FFmpeg. Única dependência externa: Pillow."""
__version__ = "0.1.0"


def __getattr__(name):  # imports preguiçosos: video/image funcionam sem Kivy
    if name == "Capture":
        from .capture import Capture
        return Capture
    if name in ("AviMjpegWriter", "AsyncVideoRecorder"):
        from . import video
        return getattr(video, name)
    if name in ("Region", "Target"):
        from . import region
        return getattr(region, name)
    if name in ("select_region", "pick_widget"):
        from . import selector
        return getattr(selector, name)
    if name in ("rgba_to_pil", "save_image"):
        from . import image
        return getattr(image, name)
    raise AttributeError(name)
