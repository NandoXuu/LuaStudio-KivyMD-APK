import base64
import json
import math
import os
import struct
from bisect import bisect_right
from urllib.parse import unquote

IDENTITY = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
DEFAULT_COLOR = (0.8, 0.8, 0.8, 1.0)
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
COMPONENT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
NORMAL_DIVISOR = {"b": 127.0, "B": 255.0, "h": 32767.0, "H": 65535.0, "I": 4294967295.0}
ELEMENT_COUNT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
EXTENSIONS = (".obj", ".gltf", ".glb")


class TextureRef(object):
    __slots__ = ("key", "path", "data", "ext")

    def __init__(self, key, path=None, data=None, ext=None):
        self.key = key
        self.path = path
        self.data = data
        self.ext = ext


class Submesh(object):
    __slots__ = ("name", "positions", "uvs", "triangles", "node", "joints", "weights",
                 "skin_nodes", "inv_bind", "texture", "color")

    def __init__(self, name, positions, uvs, triangles, node=-1, joints=None, weights=None,
                 skin_nodes=None, inv_bind=None, texture=None, color=DEFAULT_COLOR):
        self.name = name
        self.positions = positions
        self.uvs = uvs
        self.triangles = triangles
        self.node = node
        self.joints = joints
        self.weights = weights
        self.skin_nodes = skin_nodes
        self.inv_bind = inv_bind
        self.texture = texture
        self.color = color


class Node(object):
    __slots__ = ("name", "parent", "t", "r", "s")

    def __init__(self, name, parent, t=(0.0, 0.0, 0.0), r=(0.0, 0.0, 0.0, 1.0), s=(1.0, 1.0, 1.0)):
        self.name = name
        self.parent = parent
        self.t = t
        self.r = r
        self.s = s


class Channel(object):
    __slots__ = ("kind", "times", "values", "step")

    def __init__(self, kind, times, values, step=False):
        self.kind = kind
        self.times = times
        self.values = values
        self.step = step

    def sample(self, t):
        ts, vs = self.times, self.values
        if not ts:
            return None
        if t <= ts[0]:
            return vs[0]
        if t >= ts[-1]:
            return vs[-1]
        i = bisect_right(ts, t) - 1
        if self.step:
            return vs[i]
        t0, t1 = ts[i], ts[i + 1]
        a = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
        if self.kind == "r":
            return q_nlerp(vs[i], vs[i + 1], a)
        return lerp_vec(vs[i], vs[i + 1], a)


class Clip(object):
    __slots__ = ("name", "duration", "loop", "tracks")

    def __init__(self, name, duration, loop, tracks):
        self.name = name
        self.duration = duration
        self.loop = loop
        self.tracks = tracks

    def sample(self, time, index_of):
        pose = {}
        for node_name, channels in self.tracks.items():
            idx = index_of.get(node_name)
            if idx is None:
                continue
            entry = {}
            for kind, channel in channels.items():
                value = channel.sample(time)
                if value is not None:
                    entry[kind] = value
            if entry:
                pose[idx] = entry
        return pose


class Model(object):
    def __init__(self, name, path, submeshes, nodes, clips, textures):
        self.name = name
        self.path = path
        self.submeshes = submeshes
        self.nodes = nodes
        self.clips = clips
        self.textures = textures
        self.index_of = {}
        for i, node in enumerate(nodes):
            self.index_of.setdefault(node.name, i)
        self.order = _topological(nodes)
        self.rest_world = world_matrices(self, {})

    def triangle_count(self):
        return sum(len(sm.triangles) for sm in self.submeshes)


def _topological(nodes):
    children = {}
    roots = []
    for i, node in enumerate(nodes):
        if node.parent < 0:
            roots.append(i)
        else:
            children.setdefault(node.parent, []).append(i)
    order = []
    stack = list(reversed(roots))
    while stack:
        i = stack.pop()
        order.append(i)
        stack.extend(reversed(children.get(i, [])))
    return order


def mat_mul(a, b):
    bt = list(zip(*b))
    return [[a[i][0] * bt[j][0] + a[i][1] * bt[j][1] + a[i][2] * bt[j][2] + a[i][3] * bt[j][3]
             for j in range(4)] for i in range(4)]


def xform_point(m, p):
    x, y, z = p
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def mat_from_trs(t, r, s):
    x, y, z, w = r
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    r00, r01, r02 = 1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)
    r10, r11, r12 = 2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)
    r20, r21, r22 = 2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)
    sx, sy, sz = s
    return [[r00 * sx, r01 * sy, r02 * sz, t[0]],
            [r10 * sx, r11 * sy, r12 * sz, t[1]],
            [r20 * sx, r21 * sy, r22 * sz, t[2]],
            [0.0, 0.0, 0.0, 1.0]]


def world_matrices(model, pose):
    world = [None] * len(model.nodes)
    for i in model.order:
        node = model.nodes[i]
        over = pose.get(i) or {}
        local = mat_from_trs(over.get("t", node.t), over.get("r", node.r), over.get("s", node.s))
        world[i] = local if node.parent < 0 else mat_mul(world[node.parent], local)
    return world


def evaluate(model, pose):
    if not pose and model.rest_world is not None:
        world = model.rest_world
    else:
        world = world_matrices(model, pose)
    out = []
    for sm in model.submeshes:
        if sm.skin_nodes:
            skins = [mat_mul(world[j], inv) for j, inv in zip(sm.skin_nodes, sm.inv_bind)]
            pts = []
            for p, jt, wt in zip(sm.positions, sm.joints, sm.weights):
                x = y = z = 0.0
                for k in range(4):
                    w = wt[k]
                    if w == 0.0:
                        continue
                    m = skins[jt[k]]
                    x += w * (m[0][0] * p[0] + m[0][1] * p[1] + m[0][2] * p[2] + m[0][3])
                    y += w * (m[1][0] * p[0] + m[1][1] * p[1] + m[1][2] * p[2] + m[1][3])
                    z += w * (m[2][0] * p[0] + m[2][1] * p[1] + m[2][2] * p[2] + m[2][3])
                pts.append((x, y, z))
        elif sm.node >= 0:
            m = world[sm.node]
            pts = [xform_point(m, p) for p in sm.positions]
        else:
            pts = sm.positions
        out.append((sm, pts))
    return out


def lerp_vec(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))


def q_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def q_normalize(q):
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def q_nlerp(a, b, t):
    if sum(a[i] * b[i] for i in range(4)) < 0.0:
        b = tuple(-c for c in b)
    return q_normalize(tuple(a[i] + (b[i] - a[i]) * t for i in range(4)))


def quat_from_euler(x, y, z):
    def axis(angle, idx):
        h = math.radians(angle) * 0.5
        q = [0.0, 0.0, 0.0, math.cos(h)]
        q[idx] = math.sin(h)
        return tuple(q)
    return q_normalize(q_mul(axis(z, 2), q_mul(axis(y, 1), axis(x, 0))))


def quat_from_mat3(m):
    m00, m01, m02 = m[0]
    m10, m11, m12 = m[1]
    m20, m21, m22 = m[2]
    tr = m00 + m11 + m22
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        q = (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        q = 0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        q = (m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        q = (m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s
    return q_normalize(q)


def decompose_matrix(flat):
    cols = [[flat[c * 4 + r] for r in range(4)] for c in range(4)]
    t = tuple(cols[3][:3])
    sx = math.sqrt(sum(v * v for v in cols[0][:3])) or 1.0
    sy = math.sqrt(sum(v * v for v in cols[1][:3])) or 1.0
    sz = math.sqrt(sum(v * v for v in cols[2][:3])) or 1.0
    rot = [[cols[0][r] / sx, cols[1][r] / sy, cols[2][r] / sz] for r in range(3)]
    return t, quat_from_mat3(rot), (sx, sy, sz)


def compute_normals(positions, triangles):
    acc = [[0.0, 0.0, 0.0] for _ in positions]
    for a, b, c in triangles:
        pa, pb, pc = positions[a], positions[b], positions[c]
        u = (pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2])
        v = (pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2])
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        for i in (a, b, c):
            acc[i][0] += n[0]
            acc[i][1] += n[1]
            acc[i][2] += n[2]
    return acc


def _resolve_file(base_dir, uri):
    return os.path.normpath(os.path.join(base_dir, unquote(uri)))


def _parse_mtl(path, materials, textures, model_key):
    if not os.path.isfile(path):
        return
    base = os.path.dirname(path)
    current = None
    with open(path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 2:
                continue
            tag = parts[0]
            if tag == "newmtl":
                current = " ".join(parts[1:])
                materials[current] = {"color": DEFAULT_COLOR, "texture": None}
            elif current is None:
                continue
            elif tag == "Kd" and len(parts) >= 4:
                alpha = materials[current]["color"][3]
                materials[current]["color"] = (float(parts[1]), float(parts[2]), float(parts[3]), alpha)
            elif tag == "d":
                c = materials[current]["color"]
                materials[current]["color"] = (c[0], c[1], c[2], float(parts[1]))
            elif tag == "map_Kd":
                file_path = _resolve_file(base, " ".join(parts[1:]))
                key = "file:" + file_path
                textures.setdefault(key, TextureRef(key, path=file_path))
                materials[current]["texture"] = key


def _obj_corner(token, count_v, count_t, count_n):
    parts = token.split("/")
    vi = int(parts[0])
    vi = vi - 1 if vi > 0 else count_v + vi
    ti = -1
    if len(parts) > 1 and parts[1]:
        ti = int(parts[1])
        ti = ti - 1 if ti > 0 else count_t + ti
    return vi, ti


def load_obj(path):
    positions, uvs = [], []
    materials = {}
    textures = {}
    groups = {}
    order = []
    current = "__default"
    base = os.path.dirname(path)
    with open(path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            parts = line.split()
            if not parts or parts[0].startswith("#"):
                continue
            tag = parts[0]
            if tag == "v":
                positions.append((float(parts[1]), float(parts[2]), float(parts[3])))
            elif tag == "vt":
                uvs.append((float(parts[1]), float(parts[2]) if len(parts) > 2 else 0.0))
            elif tag == "mtllib":
                for name in parts[1:]:
                    _parse_mtl(_resolve_file(base, name), materials, textures, path)
            elif tag == "usemtl":
                current = " ".join(parts[1:])
            elif tag == "f":
                group = groups.get(current)
                if group is None:
                    group = {"verts": [], "uvs": [], "tris": [], "map": {}}
                    groups[current] = group
                    order.append(current)
                face = []
                for token in parts[1:]:
                    key = _obj_corner(token, len(positions), len(uvs), 0)
                    idx = group["map"].get(key)
                    if idx is None:
                        idx = len(group["verts"])
                        group["map"][key] = idx
                        group["verts"].append(positions[key[0]])
                        group["uvs"].append(uvs[key[1]] if key[1] >= 0 else (0.0, 0.0))
                    face.append(idx)
                for k in range(1, len(face) - 1):
                    group["tris"].append((face[0], face[k], face[k + 1]))
    submeshes = []
    for name in order:
        group = groups[name]
        if not group["tris"]:
            continue
        mat = materials.get(name, {"color": DEFAULT_COLOR, "texture": None})
        submeshes.append(Submesh(name, group["verts"], group["uvs"], group["tris"],
                                 texture=textures.get(mat["texture"]) if mat["texture"] else None,
                                 color=mat["color"]))
    if not submeshes:
        raise ValueError("o arquivo OBJ nao contem faces")
    name = os.path.basename(path)
    return Model(name, path, submeshes, [], {}, list(textures.values()))


def _parse_glb(data):
    offset = 12
    doc, binary = None, None
    while offset + 8 <= len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        body = data[offset + 8: offset + 8 + length]
        if kind == JSON_CHUNK:
            doc = json.loads(body.decode("utf-8"))
        elif kind == BIN_CHUNK:
            binary = body
        offset += 8 + length
    if doc is None:
        raise ValueError("GLB sem bloco JSON")
    return doc, binary


class _Gltf(object):
    def __init__(self, doc, binary, path):
        self.doc = doc
        self.base = os.path.dirname(path)
        self.path = path
        self.buffers = []
        for buffer in doc.get("buffers", []):
            uri = buffer.get("uri")
            if uri is None:
                self.buffers.append(binary or b"")
            elif uri.startswith("data:"):
                self.buffers.append(base64.b64decode(uri.split(",", 1)[1]))
            else:
                with open(_resolve_file(self.base, uri), "rb") as handle:
                    self.buffers.append(handle.read())
        self.texture_cache = {}

    def accessor(self, index):
        acc = self.doc["accessors"][index]
        code, size = COMPONENT[acc["componentType"]]
        n = ELEMENT_COUNT[acc["type"]]
        count = acc["count"]
        if "bufferView" not in acc:
            return [(0.0,) * n] * count
        view = self.doc["bufferViews"][acc["bufferView"]]
        data = self.buffers[view["buffer"]]
        offset = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = view.get("byteStride", size * n)
        fmt = "<" + code * n
        normalized = acc.get("normalized", False) and code in NORMAL_DIVISOR
        out = []
        for i in range(count):
            vals = struct.unpack_from(fmt, data, offset + i * stride)
            if normalized:
                vals = tuple(v / NORMAL_DIVISOR[code] for v in vals)
            out.append(vals)
        return out

    def matrices(self, index):
        flat = self.accessor(index)
        result = []
        for vals in flat:
            result.append([[vals[c * 4 + r] for c in range(4)] for r in range(4)])
        return result

    def texture(self, texture_index, model_key):
        source = self.doc["textures"][texture_index].get("source")
        if source is None:
            return None
        if source in self.texture_cache:
            return self.texture_cache[source]
        image = self.doc["images"][source]
        ref = None
        if "bufferView" in image:
            view = self.doc["bufferViews"][image["bufferView"]]
            start = view.get("byteOffset", 0)
            data = bytes(self.buffers[view["buffer"]][start:start + view["byteLength"]])
            mime = image.get("mimeType", "image/png")
            ext = "png" if "png" in mime else "jpg"
            ref = TextureRef("mem:%s:%d" % (model_key, source), data=data, ext=ext)
        elif "uri" in image:
            uri = image["uri"]
            if uri.startswith("data:"):
                mime = uri[5:uri.index(";")] if ";" in uri else "image/png"
                data = base64.b64decode(uri.split(",", 1)[1])
                ext = "png" if "png" in mime else "jpg"
                ref = TextureRef("mem:%s:%d" % (model_key, source), data=data, ext=ext)
            else:
                file_path = _resolve_file(self.base, uri)
                ref = TextureRef("file:" + file_path, path=file_path)
        self.texture_cache[source] = ref
        return ref

    def local_trs(self, node):
        if "matrix" in node:
            return decompose_matrix(node["matrix"])
        return (tuple(node.get("translation", (0.0, 0.0, 0.0))),
                tuple(node.get("rotation", (0.0, 0.0, 0.0, 1.0))),
                tuple(node.get("scale", (1.0, 1.0, 1.0))))


def _unique_names(raw):
    seen = {}
    names = []
    for i, name in enumerate(raw):
        base = name or "node_%d" % i
        count = seen.get(base, 0)
        seen[base] = count + 1
        names.append(base if count == 0 else "%s#%d" % (base, count + 1))
    return names


def load_gltf(path):
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:4] == b"glTF":
        doc, binary = _parse_glb(data)
    else:
        doc, binary = json.loads(data.decode("utf-8")), None
    src = _Gltf(doc, binary, path)
    model_key = os.path.basename(path)
    node_defs = doc.get("nodes", [])
    names = _unique_names([n.get("name") for n in node_defs])
    parent = {}
    for i, node in enumerate(node_defs):
        for child in node.get("children", []):
            parent[child] = i
    nodes = []
    for i, node in enumerate(node_defs):
        t, r, s = src.local_trs(node)
        nodes.append(Node(names[i], parent.get(i, -1), t, r, s))

    skin_joint_map = {}
    skins = []
    for skin_index, skin in enumerate(doc.get("skins", [])):
        joints = skin["joints"]
        if "inverseBindMatrices" in skin:
            inverse = src.matrices(skin["inverseBindMatrices"])
        else:
            inverse = [IDENTITY] * len(joints)
        skins.append((joints, inverse))
        skin_joint_map[skin_index] = True

    submeshes = []
    for node_index, node in enumerate(node_defs):
        if "mesh" not in node:
            continue
        mesh = doc["meshes"][node["mesh"]]
        for prim_index, prim in enumerate(mesh["primitives"]):
            if prim.get("mode", 4) != 4:
                continue
            attrs = prim["attributes"]
            positions = [tuple(p) for p in src.accessor(attrs["POSITION"])]
            if "indices" in prim:
                flat = [v[0] for v in src.accessor(prim["indices"])]
            else:
                flat = list(range(len(positions)))
            triangles = [(flat[i], flat[i + 1], flat[i + 2]) for i in range(0, len(flat) - 2, 3)]
            uvs = [tuple(uv[:2]) for uv in src.accessor(attrs["TEXCOORD_0"])] if "TEXCOORD_0" in attrs \
                else [(0.0, 0.0)] * len(positions)
            color = DEFAULT_COLOR
            texture = None
            if "material" in prim:
                pbr = doc["materials"][prim["material"]].get("pbrMetallicRoughness", {})
                if "baseColorFactor" in pbr:
                    color = tuple(pbr["baseColorFactor"])
                info = pbr.get("baseColorTexture")
                if info is not None:
                    texture = src.texture(info["index"], model_key)
            name = "%s/%s" % (names[node_index], mesh.get("name", "malha%d" % prim_index))
            if "skin" in node and "JOINTS_0" in attrs and "WEIGHTS_0" in attrs and node["skin"] in skin_joint_map:
                joints_nodes, inverse = skins[node["skin"]]
                joints = [tuple(int(v) for v in j) for j in src.accessor(attrs["JOINTS_0"])]
                weights = [tuple(float(v) for v in w) for w in src.accessor(attrs["WEIGHTS_0"])]
                submeshes.append(Submesh(name, positions, uvs, triangles, node=-1, joints=joints,
                                         weights=weights, skin_nodes=list(joints_nodes),
                                         inv_bind=inverse, texture=texture, color=color))
            else:
                submeshes.append(Submesh(name, positions, uvs, triangles, node=node_index,
                                         texture=texture, color=color))

    clips = {}
    for number, anim in enumerate(doc.get("animations", []), start=1):
        tracks = {}
        duration = 0.0
        for channel in anim.get("channels", []):
            target = channel["target"]
            path_kind = target.get("path")
            kind = {"translation": "t", "rotation": "r", "scale": "s"}.get(path_kind)
            if kind is None or "node" not in target:
                continue
            sampler = anim["samplers"][channel["sampler"]]
            times = [float(v[0]) for v in src.accessor(sampler["input"])]
            values = [tuple(v) for v in src.accessor(sampler["output"])]
            if sampler.get("interpolation") == "CUBICSPLINE":
                values = values[1::3]
            if kind == "r":
                values = [q_normalize(v) for v in values]
            step = sampler.get("interpolation") == "STEP"
            if not times:
                continue
            duration = max(duration, times[-1])
            node_name = names[target["node"]]
            tracks.setdefault(node_name, {})[kind] = Channel(kind, times, values, step)
        if tracks:
            clip_name = anim.get("name") or "Animacao%d" % number
            clips[clip_name] = Clip(clip_name, duration, True, tracks)

    textures = []
    for sm in submeshes:
        if sm.texture is not None and sm.texture not in textures:
            textures.append(sm.texture)
    return Model(os.path.basename(path), path, submeshes, nodes, clips, textures)


LOADERS = {".obj": load_obj, ".gltf": load_gltf, ".glb": load_gltf}
_CACHE = {}


def load_model(path):
    ext = os.path.splitext(path)[1].lower()
    loader = LOADERS.get(ext)
    if loader is None:
        raise ValueError("formato nao suportado: %s (use .obj, .gltf ou .glb)" % (ext or "?"))
    stamp = os.path.getmtime(path)
    cached = _CACHE.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    model = loader(path)
    _CACHE[path] = (stamp, model)
    return model


def _lower_keys(table):
    return dict((str(k).lower(), v) for k, v in table.items())


def clip_from_spec(name, spec):
    spec = _lower_keys(spec)
    loop = bool(spec.get("loop", True))
    declared = float(spec.get("duration") or 0.0)
    tracks = {}
    duration = declared
    for node_name, keys in (spec.get("tracks") or {}).items():
        buckets = {"t": [], "r": [], "s": []}
        items = keys if isinstance(keys, list) else list(keys.values())
        for raw in items:
            key = _lower_keys(raw)
            time = float(key.get("t", key.get("time", 0.0)))
            pos = key.get("pos", key.get("position"))
            rot = key.get("rot", key.get("rotation"))
            scl = key.get("scale")
            if pos is not None:
                buckets["t"].append((time, _vec3(pos, (0.0, 0.0, 0.0))))
            if rot is not None:
                buckets["r"].append((time, _quat(rot)))
            if scl is not None:
                buckets["s"].append((time, _vec3(scl, (1.0, 1.0, 1.0))))
        channels = {}
        for kind, entries in buckets.items():
            if not entries:
                continue
            entries.sort(key=lambda e: e[0])
            times = [e[0] for e in entries]
            values = [e[1] for e in entries]
            duration = max(duration, times[-1])
            channels[kind] = Channel(kind, times, values)
        if channels:
            tracks[str(node_name)] = channels
    return Clip(name, duration, loop, tracks)


def _vec3(value, default):
    if isinstance(value, dict):
        return (float(value.get("x", default[0])), float(value.get("y", default[1])),
                float(value.get("z", default[2])))
    vals = [float(v) for v in list(value)[:3]]
    while len(vals) < 3:
        vals.append(default[len(vals)])
    return tuple(vals)


def _quat(value):
    if isinstance(value, dict) and "w" in value:
        return q_normalize(tuple(float(value.get(k, 0.0)) for k in ("x", "y", "z", "w")))
    if isinstance(value, dict):
        return quat_from_euler(*_vec3(value, (0.0, 0.0, 0.0)))
    vals = [float(v) for v in list(value)]
    if len(vals) == 4:
        return q_normalize(tuple(vals))
    padded = (vals + [0.0, 0.0, 0.0])[:3]
    return quat_from_euler(*padded)
