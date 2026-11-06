# -*- coding: utf-8 -*-
"""API PostProcessing que reutiliza o passe ColorCalibration HDR/SDR existente."""
from .lua import LuaTable, LuaError


class PostProcessingAPI(object):
    _MAP = {
        "Exposure": "brightness", "Brightness": "brightness",
        "Contrast": "contrast", "Saturation": "saturation",
        "Highlights": "highlights", "Shadows": "shadows",
        "BlackPoint": "black_point", "WhitePoint": "white_point",
    }

    def __init__(self, runtime):
        self.rt = runtime
        self.temperature = 0.0
        self.tint = 0.0
        self._enabled = bool(runtime.render["color_calibration"]["enabled"])

    def _set_rgb_balance(self):
        # Balanço aproximado de temperatura/tint aplicado em luz linear.
        t, g = self.temperature, self.tint
        gain = [max(0.0, min(4.0, 1.0 + 0.12*t + 0.08*g)),
                max(0.0, min(4.0, 1.0 - 0.04*g)),
                max(0.0, min(4.0, 1.0 - 0.12*t + 0.08*g))]
        self.rt.set_color_calibration("rgb_gain", gain)

    def set(self, *args):
        if not args or not isinstance(args[-1], LuaTable):
            raise LuaError("Graphics.PostProcessing.Set espera uma tabela")
        explicit_enabled = None
        has_visual_parameter = False
        for key, value in args[-1].items():
            key = str(key)
            if key == "Enabled":
                explicit_enabled = bool(value)
                self._enabled = explicit_enabled
                self.rt.set_color_calibration("enabled", explicit_enabled)
            elif key in self._MAP:
                has_visual_parameter = True
                self.rt.set_color_calibration(self._MAP[key], value)
            elif key == "Temperature":
                has_visual_parameter = True
                self.temperature = max(-1.0, min(1.0, float(value)))
                self._set_rgb_balance()
            elif key == "Tint":
                has_visual_parameter = True
                self.tint = max(-1.0, min(1.0, float(value)))
                self._set_rgb_balance()
            else:
                self.rt.log("[PostProcessing] parametro ainda nao suportado: %s" % key)
        if has_visual_parameter and explicit_enabled is not False:
            self._enabled = True
            self.rt.set_color_calibration("enabled", True)
        return True

    def get(self, *_args):
        cfg = self.rt.render["color_calibration"]
        t = LuaTable()
        for public, internal in self._MAP.items():
            t.set(public, cfg[internal])
        t.set("Enabled", bool(cfg["enabled"]))
        t.set("Temperature", self.temperature)
        t.set("Tint", self.tint)
        return t

    def reset(self, *_args):
        from .colorcal import default_color_calibration_config
        self.rt.render["color_calibration"] = default_color_calibration_config()
        self.temperature = self.tint = 0.0
        self._enabled = False
        if self.rt.render_hook:
            try:
                self.rt.render_hook("color_calibration")
            except Exception as ex:
                self.rt.log("[PostProcessing] falha ao atualizar render: %s" % ex)
        return True

    def lua_index(self, key):
        key = str(key)
        if key == "Enabled":
            return bool(self.rt.render["color_calibration"]["enabled"])
        if key == "Exposure" or key == "Brightness":
            return self.rt.render["color_calibration"]["brightness"]
        if key in self._MAP:
            return self.rt.render["color_calibration"][self._MAP[key]]
        if key == "Temperature":
            return self.temperature
        if key == "Tint":
            return self.tint
        return getattr(self, "m_" + key, None)

    def lua_newindex(self, key, value):
        key = str(key)
        if key == "Enabled":
            self._enabled = bool(value)
            self.rt.set_color_calibration("enabled", self._enabled)
        elif key in self._MAP:
            self.rt.set_color_calibration(self._MAP[key], value)
            self.rt.set_color_calibration("enabled", True)
        elif key == "Temperature":
            self.temperature = max(-1.0, min(1.0, float(value)))
            self._set_rgb_balance()
            self.rt.set_color_calibration("enabled", True)
        elif key == "Tint":
            self.tint = max(-1.0, min(1.0, float(value)))
            self._set_rgb_balance()
            self.rt.set_color_calibration("enabled", True)
        else:
            self.rt.log("[PostProcessing] propriedade desconhecida: %s" % key)

    def m_Set(self, *args):
        return self.set(*args)

    def m_Get(self, *args):
        return self.get(*args)

    def m_Reset(self, *args):
        return self.reset(*args)
