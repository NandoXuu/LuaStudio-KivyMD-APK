import json

from .lua import LuaTable, truthy
from . import model3d


def _opt(opts, key, default=None):
    if isinstance(opts, LuaTable):
        value = opts.get(key)
    elif isinstance(opts, dict):
        value = opts.get(key)
    else:
        value = None
    return default if value is None else value


def _num(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def mix_poses(model, pose_a, pose_b, amount):
    out = {}
    for idx in set(pose_a) | set(pose_b):
        ea = pose_a.get(idx) or {}
        eb = pose_b.get(idx) or {}
        node = model.nodes[idx]
        entry = {}
        entry["t"] = model3d.lerp_vec(ea.get("t", node.t), eb.get("t", node.t), amount)
        entry["r"] = model3d.q_nlerp(ea.get("r", node.r), eb.get("r", node.r), amount)
        entry["s"] = model3d.lerp_vec(ea.get("s", node.s), eb.get("s", node.s), amount)
        out[idx] = entry
    return out


class AnimPlayer(object):
    def __init__(self, inst):
        self.inst = inst
        self.clip = None
        self.name = None
        self.time = 0.0
        self.speed = 1.0
        self.loop = True
        self.playing = False
        self.on_end = None
        self.blend_total = 0.0
        self.blend_left = 0.0
        self.prev_pose = None


class AnimationService(object):
    def __init__(self, runtime):
        self.rt = runtime
        self.registry = {}

    def define(self, name, spec):
        plain = spec.to_python() if isinstance(spec, LuaTable) else dict(spec or {})
        clip = model3d.clip_from_spec(str(name), plain)
        self.registry[str(name)] = clip
        return clip

    def load_file(self, path):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        clips = data.get("clips", []) if isinstance(data, dict) else data
        count = 0
        for item in clips:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            self.define(item["name"], item)
            count += 1
        return count

    def names(self, inst=None):
        names = list(self.registry)
        if inst is not None and inst.model is not None:
            for name in inst.model.clips:
                if name not in names:
                    names.append(name)
        return names

    def find(self, inst, name):
        if inst.model is not None and name in inst.model.clips:
            return inst.model.clips[name]
        return self.registry.get(name)

    def play(self, inst, name, opts=None):
        p = inst.anim
        if p is None or inst.model is None:
            self.rt.log("[Animation] o objeto '%s' nao tem modelo carregado" % inst.name)
            return False
        clip = self.find(inst, str(name))
        if clip is None:
            self.rt.log("[Animation] clipe \"%s\" nao existe (em %s e no registro)" % (name, inst.model.name))
            return False
        blend = max(0.0, _num(_opt(opts, "Blend"), 0.0))
        if blend > 0.0 and (p.clip is not None or p.prev_pose is not None):
            p.prev_pose = self.pose_for(inst)
            p.blend_total = blend
            p.blend_left = blend
        else:
            p.prev_pose = None
            p.blend_total = 0.0
            p.blend_left = 0.0
        p.clip = clip
        p.name = str(name)
        p.speed = _num(_opt(opts, "Speed"), 1.0)
        p.loop = truthy(_opt(opts, "Loop", clip.loop))
        p.time = max(0.0, _num(_opt(opts, "Time"), 0.0))
        p.on_end = _opt(opts, "OnEnd")
        p.playing = True
        inst.geom = None
        return True

    def stop(self, inst):
        p = inst.anim
        if p is None:
            return
        p.clip = None
        p.name = None
        p.time = 0.0
        p.playing = False
        p.prev_pose = None
        p.blend_left = 0.0
        p.on_end = None
        inst.geom = None

    def pause(self, inst):
        if inst.anim is not None:
            inst.anim.playing = False

    def resume(self, inst):
        p = inst.anim
        if p is not None and p.clip is not None:
            p.playing = True

    def set_time(self, inst, seconds):
        p = inst.anim
        if p is None:
            return
        p.time = max(0.0, _num(seconds, 0.0))
        inst.geom = None

    def set_speed(self, inst, speed):
        if inst.anim is not None:
            inst.anim.speed = _num(speed, 1.0)

    def pose_for(self, inst):
        p = inst.anim
        if p is None or inst.model is None:
            return {}
        cur = p.clip.sample(p.time, inst.model.index_of) if p.clip is not None else {}
        if p.blend_left > 0.0 and p.prev_pose is not None and p.blend_total > 0.0:
            amount = 1.0 - p.blend_left / p.blend_total
            return mix_poses(inst.model, p.prev_pose, cur, amount)
        return cur

    def step(self, dt):
        for inst in self.rt.scene.of_class("model"):
            p = inst.anim
            if p is None or inst.model is None:
                continue
            if not p.playing and p.blend_left <= 0.0:
                continue
            if p.blend_left > 0.0:
                p.blend_left = max(0.0, p.blend_left - dt)
                if p.blend_left == 0.0:
                    p.prev_pose = None
            if p.playing and p.clip is not None:
                self._advance(inst, p, dt)
            inst.geom = None

    def _advance(self, inst, p, dt):
        duration = p.clip.duration
        p.time += dt * p.speed
        if p.loop and duration > 0.0:
            p.time %= duration
            return
        if p.time >= duration or p.time < 0.0:
            p.time = min(max(p.time, 0.0), duration)
            p.playing = False
            if p.on_end is not None:
                self.rt.call(p.on_end, inst)

    def reset(self):
        self.registry = {}
