import math

from .api import to_color, to_vec, vec_table, safe_float
from .lua import LuaTable

DEFAULTS = {
    "FogColor": (0.10, 0.12, 0.18, 1.0),
    "FogStart": 0.0,
    "FogEnd": 0.0,
    "Ambient": 0.35,
    "SunDirection": (0.4, -0.9, 0.5),
    "SunIntensity": 0.85,
    "SunColor": (1.0, 0.97, 0.9, 1.0),
    "FogDensity": 0.0,
    "SkyTop": (0.08, 0.16, 0.32, 1.0),
    "SkyBottom": (0.55, 0.68, 0.82, 1.0),
    "DayNight": False,
    "DayLength": 600.0,
    "WorldTime": 0.25,
    # Skybox cubica real: seis texturas independentes (caminhos relativos ao projeto).
    "SkyboxEnabled": False,
    "SkyboxRight": "", "SkyboxLeft": "", "SkyboxTop": "",
    "SkyboxBottom": "", "SkyboxFront": "", "SkyboxBack": "",
    "SkyboxSize": 500.0,
    # Compatibilidade: panorama/equiretangular opcional.
    "SkyTexture": "",
    "SkyScale": 1.0,
    "SkyOffsetX": 0.0,
    "SkyOffsetY": 0.0,
    "SkyWidth": 1.0,
    "SkyHeight": 1.0,
    "SunTexture": "assets/engine/sun.png",
    "SunSize": 96.0,
    "SunEnabled": True,
    "SunOrbit": True,
}

KEYS = tuple(DEFAULTS)


def _normalize(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) or 1.0
    return (v[0] / n, v[1] / n, v[2] / n)


class Environment(object):
    def __init__(self):
        self.values = {}
        self.reset()

    def reset(self):
        self.values = dict(DEFAULTS)
        self._rebuild()

    def set(self, key, value):
        if key not in DEFAULTS:
            return False
        if key in ("FogColor", "SunColor", "SkyTop", "SkyBottom"):
            self.values[key] = to_color(value, DEFAULTS[key])
        elif key == "SunDirection":
            self.values[key] = to_vec(value, DEFAULTS[key])
        elif key in ("DayNight", "SunEnabled", "SunOrbit", "SkyboxEnabled"):
            self.values[key] = bool(value)
        elif key in ("SkyTexture", "SunTexture", "SkyboxRight", "SkyboxLeft", "SkyboxTop", "SkyboxBottom", "SkyboxFront", "SkyboxBack"):
            self.values[key] = str(value or "")
        else:
            self.values[key] = safe_float(value, DEFAULTS[key])
            if key == "DayLength": self.values[key] = max(10.0, self.values[key])
            if key == "SkyboxSize": self.values[key] = max(10.0, min(100000.0, self.values[key]))
            if key == "FogDensity": self.values[key] = max(0.0, self.values[key])
            if key == "WorldTime": self.values[key] = self.values[key] % 1.0
            if key in ("SkyScale", "SkyWidth", "SkyHeight"): self.values[key] = max(0.05, min(8.0, self.values[key]))
            if key == "SunSize": self.values[key] = max(1.0, min(2048.0, self.values[key]))
        self._rebuild()
        return True

    def set_config(self, config):
        """Aplica varias propriedades e devolve as chaves não reconhecidas."""
        unknown=[]
        if not isinstance(config, dict): return list(config) if config else []
        for key,value in config.items():
            if not self.set(str(key),value): unknown.append(str(key))
        return unknown

    def tick(self, dt):
        """Avança o relógio do mundo e atualiza iluminação se DayNight estiver ligado."""
        if not self.values.get("DayNight"): return
        length=max(10.0,float(self.values.get("DayLength",600.0)))
        phase=(float(self.values.get("WorldTime",0.25))+max(0.0,float(dt))/length)%1.0
        self.values["WorldTime"]=phase
        # Sol percorre o céu; intensidade suave evita um corte brusco noite/dia.
        angle=phase*2.0*math.pi
        elevation=math.sin(angle)
        if self.values.get("SunOrbit", True):
            self.values["SunDirection"]=(math.cos(angle),-elevation,0.35)
        daylight=max(0.04,min(1.0,(elevation+0.15)/0.75))
        self.values["SunIntensity"]=daylight
        self.values["Ambient"]=0.10+0.25*daylight
        self._rebuild()

    def sky_gradient(self, amount):
        """Interpela as cores do céu (amount=0 horizonte, 1 zênite)."""
        t=max(0.0,min(1.0,float(amount)))
        a,b=self.values["SkyBottom"],self.values["SkyTop"]
        return tuple(a[i]*(1-t)+b[i]*t for i in range(4))

    def get(self, key):
        return self.values.get(key)

    def to_table(self):
        t = LuaTable()
        for key in KEYS:
            v = self.values[key]
            if key in ("FogColor", "SunColor", "SkyTop", "SkyBottom"):
                t.set(key, LuaTable([float(c) for c in v]))
            elif key == "SunDirection":
                t.set(key, vec_table(*v))
            elif isinstance(v, bool):
                t.set(key, bool(v))
            elif isinstance(v, str):
                t.set(key, v)
            else:
                t.set(key, float(v))
        return t

    def fog_enabled(self):
        return self.values["FogEnd"] > self.values["FogStart"] and self.values["FogEnd"] > 0.0

    def _rebuild(self):
        self.light_dir = _normalize(tuple(-c for c in self.values["SunDirection"]))
        sc = self.values["SunColor"]
        k = self.values["SunIntensity"]
        self.sun_rgb = (sc[0] * k, sc[1] * k, sc[2] * k)
        self.ambient = max(0.0, min(1.0, self.values["Ambient"]))

    def light_factor(self, normal):
        d = normal[0] * self.light_dir[0] + normal[1] * self.light_dir[1] + normal[2] * self.light_dir[2]
        d = d if d > 0.0 else 0.0
        a = self.ambient
        return (min(1.0, a + self.sun_rgb[0] * d),
                min(1.0, a + self.sun_rgb[1] * d),
                min(1.0, a + self.sun_rgb[2] * d))

    def fog_amount(self, depth):
        density=max(0.0,float(self.values.get("FogDensity",0.0)))
        if density > 0.0:
            # Névoa exponencial: 1 - e^(-density * distância)
            return max(0.0,min(1.0,1.0-math.exp(-density*max(0.0,float(depth)))))
        if not self.fog_enabled():
            return 0.0
        start = self.values["FogStart"]
        end = self.values["FogEnd"]
        f = (depth - start) / (end - start)
        return 0.0 if f < 0.0 else (1.0 if f > 1.0 else f)
