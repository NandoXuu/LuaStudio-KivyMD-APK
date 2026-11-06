"""API pública: Capture().screenshot() / start_recording() / stop_recording()
com alvo livre: tela toda, área (x, y, largura, altura) ou qualquer widget."""
import os
import traceback

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.logger import Logger

from . import opengl, storage
from .image import compose, save_image
from .region import Region, Target, clamp_rect, output_size, resolve_rect
from .video import AsyncVideoRecorder


class Capture:
    def __init__(self, output_dir=None, widget=None, gallery=None, strict=None,
                 region=None, isolated=False, size=None, scale=1.0, resolution=None):
        """
        output_dir : qualquer pasta (C:\\..., D:\\..., /storage/emulated/0/...).
        region     : (x, y, largura, altura) ou Region - área livre da janela.
        widget     : widget Kivy específico (janela, popup, botão, jogo...).
        isolated   : widget renderizado sozinho (True) ou como aparece na tela (False).
        size/scale : tamanho/escala do arquivo de saída.
        Tudo pode ser trocado depois (set_*) ou em cada chamada.
        """
        self.output_dir = storage.expand(output_dir) if output_dir else None
        self.target = Target(region, widget, isolated, size, scale, resolution)
        self.gallery = (output_dir is None) if gallery is None else gallery
        self.strict = (output_dir is not None) if strict is None else strict
        self.last_saved = None
        self._shots = []          # (path, quality, target, on_saved, on_error)
        self._rec = None
        self._rec_path = None
        self._rec_target = None
        self._tick = None
        self._want_frame = False
        self._bound = False
        try:   # nada disso pode derrubar o app na criação
            storage.request_permissions()
            if output_dir is not None and storage.has_all_files_access() is False:
                Logger.warning("KivyCapture: sem 'acesso a todos os arquivos'; gravar em pastas "
                               "livres pode falhar. Use Capture.request_storage_access().")
        except Exception as e:
            Logger.warning("KivyCapture: verificação de permissões ignorada (%r)" % e)

    # ---------- escolha livre do alvo ----------
    def set_fullscreen(self):
        self.target = self.target.derive(fullscreen=True); return self

    def set_region(self, x=0, y=0, width=None, height=None, unit="px", origin="top-left"):
        """Área livre. Ex.: set_region(100, 50, 640, 360)  (px da janela, topo-esquerda)."""
        self.target = self.target.derive(region=Region(x, y, width, height, unit, origin))
        return self

    def set_widget(self, widget, isolated=None):
        self.target = self.target.derive(widget=widget, isolated=isolated); return self

    def set_output(self, size=None, scale=None, resolution=None):
        """Tamanho final: size=(1280, 720) | size=(1280, None) mantém proporção | scale=0.5 | resolution='HD' (SD, HD, FULL HD, QUAD, UHD; nunca aumenta)."""
        self.target = self.target.derive(size=size, scale=scale, resolution=resolution)
        return self

    def select_region(self, on_done=None, on_cancel=None):
        """O USUÁRIO desenha a área na tela (arrastando). Vira o alvo atual."""
        from .selector import select_region as _sel

        def done(region):
            self.target = self.target.derive(region=region)
            if on_done:
                on_done(region)
        return _sel(done, on_cancel)

    def pick_widget(self, on_done=None, on_cancel=None, root=None):
        """O USUÁRIO toca num elemento da interface. Vira o alvo atual."""
        from .selector import pick_widget as _pick

        def done(widget):
            self.target = self.target.derive(widget=widget)
            if on_done:
                on_done(widget)
        return _pick(done, on_cancel, root)

    def _target(self, region, widget, isolated, size, scale, fullscreen, resolution=None):
        return self.target.derive(region, widget, isolated, size, scale, fullscreen, resolution)

    # ---------- pastas ----------
    @staticmethod
    def request_storage_access():
        """Android 11+: abre a tela para permitir gravar em qualquer pasta."""
        return storage.request_all_files_access()

    def set_output_dir(self, path):
        self.output_dir = storage.expand(path) if path else None
        self.gallery = self.output_dir is None
        self.strict = self.output_dir is not None

    def _base(self, kind):
        return self.output_dir or storage.default_dir(kind)

    def _resolve(self, name, kind, ext):
        return storage.resolve_path(name, self._base(kind), ext, strict=self.strict)

    def open_folder(self):
        storage.open_folder(self.last_saved if self.last_saved and os.path.exists(self.last_saved)
                            else self._base("image"))

    # ---------- interno ----------
    def _bind(self):
        if not self._bound:
            Window.bind(on_flip=self._on_flip)   # roda antes do swap de buffers
            self._bound = True

    def _unbind_if_idle(self):
        if self._bound and not self._shots and not self._rec:
            Window.unbind(on_flip=self._on_flip)
            self._bound = False

    @staticmethod
    def _metrics():
        win_w, win_h = Window.size
        fb_w, fb_h = opengl.window_size_px()
        return win_w, win_h, fb_w, fb_h

    def _requested_size(self, t):
        """Tamanho (px) da área pedida, sem recorte."""
        if t.widget is not None and t.isolated:
            return int(t.widget.width), int(t.widget.height)
        rect = resolve_rect(t, *self._metrics())
        return rect[2], rect[3]

    def _grab(self, t):
        """-> (dados_rgba, w, h, place, req) ou None se a área está fora da tela."""
        if t.widget is not None and t.isolated:
            data, w, h = opengl.read_widget(t.widget)
            return data, w, h, None, (w, h)
        win_w, win_h, fb_w, fb_h = self._metrics()
        rect = resolve_rect(t, win_w, win_h, fb_w, fb_h)
        c = clamp_rect(rect, fb_w, fb_h)
        if c is None:
            return None
        (cx, cy, cw, ch), place = c
        data = opengl.read_rect(cx, fb_h - (cy + ch), cw, ch)   # GL: origem embaixo
        return data, cw, ch, place, (rect[2], rect[3])

    # ---------- foto ----------
    def screenshot(self, filename=None, quality=92, on_saved=None, on_error=None,
                   region=None, widget=None, isolated=None, size=None, scale=None,
                   fullscreen=False, resolution=None):
        """Foto da tela, de uma área ou de um widget. Os argumentos region/widget/
        size/scale valem só para esta foto (senão usa o alvo atual do Capture).
        filename: None (automático), 'foto.png', 'D:/x/foto.jpg' ou 'D:/x/'."""
        try:
            path = self._resolve(filename, "image", ".png")
        except Exception as e:
            Logger.error("KivyCapture: %s" % e)
            if on_error:
                on_error(e)
                return None
            raise
        t = self._target(region, widget, isolated, size, scale, fullscreen, resolution)
        self._shots.append((path, quality, t, on_saved, on_error))
        self._bind()
        Window.canvas.ask_update()
        return str(path)

    # ---------- vídeo ----------
    def start_recording(self, filename=None, fps=30, quality=80,
                        region=None, widget=None, isolated=None, size=None, scale=None,
                        fullscreen=False, resolution=None):
        """Grava a tela, uma área ou um widget. O tamanho do vídeo é fixado ao iniciar
        (se o widget/área mudar de tamanho depois, o quadro é ajustado a ele)."""
        if self._rec:
            raise RuntimeError("Já existe uma gravação em andamento")
        t = self._target(region, widget, isolated, size, scale, fullscreen, resolution)
        rw, rh = self._requested_size(t)
        w, h = output_size(rw, rh, t.size, t.scale, even=True, resolution=t.resolution)
        self._rec_path = self._resolve(filename, "video", ".avi")
        self._rec_target = t
        self._rec = AsyncVideoRecorder(self._rec_path, w, h, fps, quality)
        self._tick = Clock.schedule_interval(self._request_frame, 1.0 / fps)
        self._bind()
        return str(self._rec_path)

    def _request_frame(self, dt):
        self._want_frame = True
        Window.canvas.ask_update()

    def stop_recording(self):
        """Finaliza o .avi. Retorna (local_final, total_de_frames, frames_descartados)."""
        if not self._rec:
            return None
        if self._tick:
            self._tick.cancel()
        rec, self._rec = self._rec, None
        try:
            frames = rec.stop()
        finally:
            self._unbind_if_idle()
        final = storage.publish(self._rec_path, gallery=self.gallery)
        if not self.gallery:
            storage.scan_media(self._rec_path)
        self.last_saved = final
        Logger.info("KivyCapture: vídeo salvo em %s" % final)
        return final, frames, rec.dropped

    @property
    def recording(self):
        return self._rec is not None

    # ---------- hook de renderização ----------
    def _on_flip(self, *a):
        if self._shots:
            shots, self._shots = self._shots, []
            for path, q, t, ok, err in shots:
                try:
                    got = self._grab(t)
                    if got is None:
                        raise ValueError("a área escolhida está fora da janela")
                    data, w, h, place, req = got
                    out = output_size(req[0], req[1], t.size, t.scale, resolution=t.resolution)
                    img = compose(data, w, h, place, req, out)
                    save_image(img, path, q)
                    if not os.path.exists(path) or os.path.getsize(path) == 0:
                        raise OSError("o arquivo não foi gravado: %s" % path)
                    final = storage.publish(path, gallery=self.gallery)
                    if not self.gallery:
                        storage.scan_media(path)
                    self.last_saved = final
                    Logger.info("KivyCapture: imagem salva em %s" % final)
                    if ok:
                        ok(final)
                except Exception as e:
                    Logger.error("KivyCapture: falha ao salvar %s: %s" % (path, traceback.format_exc()))
                    if err:
                        err(e)
        if self._rec and self._want_frame:
            self._want_frame = False
            try:
                got = self._grab(self._rec_target)
                if got is not None:             # área fora da tela: pula (vira frame repetido)
                    data, w, h, place, req = got
                    self._rec.push(data, w, h, True, place, req)
            except Exception:
                Logger.error("KivyCapture: falha ao ler frame: %s" % traceback.format_exc())
        self._unbind_if_idle()
