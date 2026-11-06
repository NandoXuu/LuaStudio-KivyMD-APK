import os

from .lua import LuaTable, LuaError, tostring
from .api import Instance, to_color
from . import model3d
from . import imagesize
from . import env3d


def _table(items):
    return LuaTable([str(x) for x in items])


def _model_info(path):
    t = LuaTable()
    t.set("Name", os.path.basename(path))
    t.set("Format", os.path.splitext(path)[1].lower().lstrip("."))
    return t


def install(rt, g):
    anim = rt.anim3d
    env = rt.env3d

    animation = LuaTable()

    def _define(name=None, spec=None):
        if name is None or not isinstance(spec, LuaTable):
            raise LuaError("Animation.define(nome, { Duration=, Loop=, Tracks={ Osso={ {Time=,Rot=,Pos=,Scale=} } } })")
        anim.define(tostring(name), spec)
        return None

    def _load(path=None):
        full = rt.resolve_asset(tostring(path or ""))
        try:
            return float(anim.load_file(full))
        except Exception as ex:
            rt.log("[Animation] nao carregou %s: %s" % (path, ex))
            return 0.0

    def _names(inst=None):
        return _table(anim.names(inst if isinstance(inst, Instance) else None))

    def _has(name=None, inst=None):
        return tostring(name) in anim.names(inst if isinstance(inst, Instance) else None)

    def _play(inst=None, name=None, opts=None):
        if not isinstance(inst, Instance) or inst.cls != "model":
            rt.log("[Animation] Animation.play espera um objeto model")
            return False
        return anim.play(inst, tostring(name), opts)

    animation.set("define", _define)
    animation.set("load", _load)
    animation.set("list", _names)
    animation.set("has", _has)
    animation.set("play", _play)
    animation.set("stop", lambda inst=None: anim.stop(inst) if isinstance(inst, Instance) else None)
    g("Animation", animation)
    g("animation", animation)

    models = LuaTable()

    def _model_info_table(path=None):
        full = rt.resolve_asset(tostring(path or ""))
        try:
            model = model3d.load_model(full)
        except Exception as ex:
            rt.log("[Models] nao carregou %s: %s" % (path, ex))
            return None
        t = _model_info(full)
        t.set("Triangles", float(model.triangle_count()))
        t.set("Submeshes", float(len(model.submeshes)))
        t.set("Textures", float(len(model.textures)))
        t.set("Bones", _table([n.name for n in model.nodes]))
        t.set("Clips", _table(sorted(model.clips)))
        return t

    def _preload(path=None):
        full = rt.resolve_asset(tostring(path or ""))
        try:
            model3d.load_model(full)
            return True
        except Exception as ex:
            rt.log("[Models] nao carregou %s: %s" % (path, ex))
            return False

    models.set("info", _model_info_table)
    models.set("preload", _preload)
    g("Models", models)
    g("models", models)

    images = LuaTable()

    def _image_info(path=None):
        full = rt.resolve_asset(tostring(path or ""))
        try:
            info = imagesize.read_image_info(full)
        except OSError:
            info = None
        if not info:
            return None
        t = LuaTable()
        t.set("Format", info["Format"])
        t.set("Width", float(info["Width"]))
        t.set("Height", float(info["Height"]))
        return t

    images.set("info", _image_info)
    images.set("exists", lambda path=None: os.path.isfile(rt.resolve_asset(tostring(path or ""))))
    g("Images", images)
    g("images", images)

    env3d_t = LuaTable()

    def _env_set(spec=None):
        if not isinstance(spec, LuaTable):
            raise LuaError("Env3D.set espera uma tabela, ex.: { FogColor = \"#202838\", FogEnd = 60 }")
        for key, value in spec.items():
            _apply(str(key), value)
        return None

    def _apply(key, value):
        lk = key.lower()
        if lk == "sky":
            rt.background = to_color(value, rt.background)
            return
        for real in env3d.KEYS:
            if real.lower() == lk:
                env.set(real, value)
                return
        rt.log("[Env3D] opcao desconhecida: %s (disponiveis: Sky, %s)" % (key, ", ".join(env3d.KEYS)))

    def _env_get(key=None):
        if key is None:
            return env.to_table()
        value = env.get(tostring(key))
        if value is None:
            return None
        table = env.to_table()
        return table.get(tostring(key))

    def _set_fog(color=None, start=None, finish=None):
        env.set("FogColor", color)
        env.set("FogStart", float(start or 0.0))
        env.set("FogEnd", float(finish or 0.0))

    def _set_sun(direction=None, intensity=None, color=None):
        if direction is not None:
            env.set("SunDirection", direction)
        if intensity is not None:
            env.set("SunIntensity", float(intensity))
        if color is not None:
            env.set("SunColor", color)

    def _set_skybox(spec=None):
        if not isinstance(spec, LuaTable):
            raise LuaError("Env3D.setSkybox espera { Right=, Left=, Top=, Bottom=, Front=, Back=, Size= }")
        aliases = {"right":"SkyboxRight", "left":"SkyboxLeft", "top":"SkyboxTop",
                   "bottom":"SkyboxBottom", "front":"SkyboxFront", "back":"SkyboxBack",
                   "size":"SkyboxSize", "enabled":"SkyboxEnabled"}
        for key, value in spec.items():
            name = aliases.get(str(key).lower())
            if name:
                env.set(name, value)
            else:
                rt.log("[Env3D] face de skybox desconhecida: %s" % key)
        env.set("SkyboxEnabled", True)
        return None

    env3d_t.set("setSkybox", _set_skybox)
    env3d_t.set("set", _env_set)
    env3d_t.set("get", _env_get)
    env3d_t.set("reset", lambda *a: env.reset())
    env3d_t.set("setFog", _set_fog)
    env3d_t.set("setSky", lambda c=None: _apply("Sky", c))
    env3d_t.set("setAmbient", lambda v=None: env.set("Ambient", float(v or 0.0)))
    env3d_t.set("setSun", _set_sun)
    g("Env3D", env3d_t)
    g("env3d", env3d_t)

    # API de sol dedicada, mantendo a implementacao do relogio em Env3D.
    sun_t = LuaTable()
    sun_t.set("setTexture", lambda path=None: env.set("SunTexture", tostring(path or "assets/engine/sun.png")))
    sun_t.set("setSize", lambda size=None: env.set("SunSize", float(size or 96.0)))
    sun_t.set("enable", lambda enabled=True: env.set("SunEnabled", enabled))
    sun_t.set("setOrbit", lambda enabled=True: env.set("SunOrbit", enabled))
    sun_t.set("setColor", lambda color=None: env.set("SunColor", color))
    sun_t.set("setDirection", lambda direction=None: env.set("SunDirection", direction))
    sun_t.set("setTime", lambda phase=None: env.set("WorldTime", float(phase or 0.0)))
    sun_t.set("getTime", lambda: float(env.get("WorldTime") or 0.0))
    sun_t.set("getEnabled", lambda: bool(env.get("SunEnabled")))
    g("Sun", sun_t)
    g("sun", sun_t)
