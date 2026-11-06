# -*- coding: utf-8 -*-
"""Bridge da API Lua Capture para a biblioteca KivyCapture."""
from .lua import LuaTable, LuaError, tostring, truthy
import copy


def _plain(value):
    if isinstance(value, LuaTable):
        out = {}
        for k, v in value.items():
            out[k] = _plain(v)
        return out
    return value


def _options(args):
    if not args:
        return {}
    value = args[-1]
    if value is None:
        return {}
    if isinstance(value, LuaTable):
        return _plain(value)
    if isinstance(value, dict):
        return value
    raise LuaError("Capture espera uma tabela de opcoes")


class CaptureAPI(object):
    def __init__(self, runtime):
        self.rt = runtime
        self._capture = None
        self._photo_active = False
        self._photo_previous = None
        self._photo_was_paused = False
        self._photo_pp_previous = None
        self.recording = LuaTable()
        self.photo = LuaTable()
        self._install()

    def _get_capture(self):
        stage = getattr(self.rt, "stage_widget", None)
        if stage is None:
            raise LuaError("Capture ainda nao esta pronto: Stage Kivy nao foi conectado")
        if self._capture is None:
            try:
                from .kivycapture import Capture
                self._capture = Capture(widget=stage, isolated=False)
            except Exception as ex:
                raise LuaError("nao foi possivel iniciar KivyCapture: %s" % ex)
        else:
            self._capture.set_widget(stage, isolated=False)
        return self._capture

    def _screenshot(self, *args):
        opts = _options(args)
        cap = self._get_capture()
        name = opts.get("Filename", opts.get("filename"))
        quality = int(opts.get("Quality", opts.get("quality", 92)))
        resolution = opts.get("Resolution", opts.get("resolution"))
        size = opts.get("Size", opts.get("size"))
        scale = opts.get("Scale", opts.get("scale"))
        fmt = str(opts.get("Format", opts.get("format", ""))).lower()
        if fmt in ("jpg", "jpeg") and name and not str(name).lower().endswith((".jpg", ".jpeg")):
            name = str(name) + ".jpg"
        elif fmt == "png" and name and not str(name).lower().endswith(".png"):
            name = str(name) + ".png"
        return cap.screenshot(filename=name, quality=quality, resolution=resolution,
                              size=tuple(size) if size else None, scale=scale)

    def _record_start(self, *args):
        opts = _options(args)
        cap = self._get_capture()
        name = opts.get("Filename", opts.get("filename"))
        fps = max(1, min(60, int(opts.get("FPS", opts.get("fps", 30)))))
        quality = max(20, min(100, int(opts.get("Quality", opts.get("quality", 80)))))
        resolution = opts.get("Resolution", opts.get("resolution"))
        size = opts.get("Size", opts.get("size"))
        scale = opts.get("Scale", opts.get("scale"))
        try:
            return cap.start_recording(filename=name, fps=fps, quality=quality,
                                       resolution=resolution,
                                       size=tuple(size) if size else None, scale=scale)
        except Exception as ex:
            raise LuaError("Capture.Recording.Start: %s" % ex)

    def _record_stop(self, *_args):
        if self._capture is None:
            return None
        try:
            result = self._capture.stop_recording()
            if result is None:
                return None
            path, frames, dropped = result
            t = LuaTable()
            t.set("Path", str(path))
            t.set("Frames", int(frames))
            t.set("DroppedFrames", int(dropped))
            return t
        except Exception as ex:
            raise LuaError("Capture.Recording.Stop: %s" % ex)

    def _recording(self, *_args):
        return bool(self._capture and self._capture.recording)

    def _photo_enable(self, *args):
        opts = _options(args)
        if self._photo_active:
            return True
        # Preserva o visual atual; os ajustes da sessao de foto sao aplicados
        # pelo mesmo passe ColorCalibration, antes do resolve HDR.
        self._photo_previous = copy.deepcopy(self.rt.render["color_calibration"])
        pp = getattr(self.rt, "postprocessing_api", None)
        self._photo_pp_previous = (pp.temperature, pp.tint) if pp is not None else None
        self._photo_was_paused = bool(self.rt.worldtime.paused)
        self._photo_active = True
        self.rt.photo_mode_options = opts
        if truthy(opts.get("FreezeGame", False)):
            self.rt.worldtime.pause()
        return True

    def _photo_disable(self, *_args):
        if not self._photo_active:
            return False
        if self._photo_previous is not None:
            self.rt.render["color_calibration"] = self._photo_previous
            if self.rt.render_hook is not None:
                try:
                    self.rt.render_hook("color_calibration")
                except Exception:
                    pass
        if not self._photo_was_paused and self.rt.worldtime.paused:
            self.rt.worldtime.resume()
        pp = getattr(self.rt, "postprocessing_api", None)
        if pp is not None and self._photo_pp_previous is not None:
            pp.temperature, pp.tint = self._photo_pp_previous
        self._photo_previous = None
        self._photo_pp_previous = None
        self._photo_active = False
        self._photo_was_paused = False
        return True

    def _photo_set(self, *args):
        opts = _options(args)
        table = LuaTable()
        for key, value in opts.items():
            table.set(key, value)
        pp = getattr(self.rt, "postprocessing_api", None)
        if pp is not None:
            pp.set(table)
        return True


    def reset(self):
        """Encerra a sessao de captura/foto antes de reiniciar os scripts Lua."""
        if self._capture is not None and self._capture.recording:
            try:
                self._capture.stop_recording()
            except Exception as ex:
                self.rt.log("[Capture] erro ao finalizar gravacao no reset: %s" % ex)
        if self._photo_active:
            self._photo_disable()

    def _install(self):
        self.recording.set("Start", self._record_start)
        self.recording.set("Stop", self._record_stop)
        self.recording.set("IsRecording", self._recording)
        self.photo.set("Enable", self._photo_enable)
        self.photo.set("Disable", self._photo_disable)
        self.photo.set("IsEnabled", lambda *_a: self._photo_active)
        self.photo.set("SetPostProcessing", self._photo_set)
        self.table = LuaTable()
        self.table.set("Screenshot", self._screenshot)
        self.table.set("Recording", self.recording)
        self.table.set("PhotoMode", self.photo)
        self.table.set("RequestStorageAccess", self._request_storage)
        self.table.set("LastSaved", lambda *_a: self._capture.last_saved if self._capture else None)

    def _request_storage(self, *_args):
        try:
            from .kivycapture import Capture
            return bool(Capture.request_storage_access())
        except Exception as ex:
            self.rt.log("[Capture] permissao de armazenamento: %s" % ex)
            return False
