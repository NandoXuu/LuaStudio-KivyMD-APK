import json
import math
import os
import struct
import zlib

RINGS = 8
SEGMENTS = 8
HEIGHT = 2.0
RADIUS = 0.3


def make_png(width, height, cell=4, a=(230, 190, 60), b=(40, 60, 120)):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            c = a if ((x // cell) + (y // cell)) % 2 == 0 else b
            raw.extend(c)
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def _pad(buf):
    while len(buf) % 4:
        buf.append(0)


def _view(buf, views, data, target=None):
    _pad(buf)
    offset = len(buf)
    buf.extend(data)
    view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
    if target is not None:
        view["target"] = target
    views.append(view)
    return len(views) - 1


def _accessor(accessors, view, count, ctype, kind, minmax=None, offset=0, stride=None):
    acc = {"bufferView": view, "componentType": ctype, "count": count, "type": kind}
    if offset:
        acc["byteOffset"] = offset
    if minmax is not None:
        acc["min"], acc["max"] = minmax
    accessors.append(acc)
    return len(accessors) - 1


def make_glb(path):
    positions, uvs, joints, weights, indices = [], [], [], [], []
    for r in range(RINGS + 1):
        y = HEIGHT * r / RINGS
        for s in range(SEGMENTS):
            ang = 2 * math.pi * s / SEGMENTS
            positions.append((RADIUS * math.cos(ang), y, RADIUS * math.sin(ang)))
            uvs.append((s / SEGMENTS, y / HEIGHT))
            if y <= 0.8:
                jt, wt = (0, 0, 0, 0), (1.0, 0.0, 0.0, 0.0)
            elif y >= 1.2:
                jt, wt = (1, 0, 0, 0), (1.0, 0.0, 0.0, 0.0)
            else:
                k = (y - 0.8) / 0.4
                jt, wt = (0, 1, 0, 0), (1.0 - k, k, 0.0, 0.0)
            joints.append(jt)
            weights.append(wt)
    for r in range(RINGS):
        for s in range(SEGMENTS):
            a = r * SEGMENTS + s
            b = r * SEGMENTS + (s + 1) % SEGMENTS
            c = (r + 1) * SEGMENTS + (s + 1) % SEGMENTS
            d = (r + 1) * SEGMENTS + s
            indices.extend([a, b, c, a, c, d])

    png = make_png(64, 64)
    inv_bind = [
        [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
        [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, -1, 0, 1],
    ]
    times = [0.0, 0.5, 1.0, 1.5, 2.0]
    idle_rot = [euler_quat(0, 0, 10 * math.sin(2 * math.pi * t / 2.0)) for t in times]
    walk_t = [0.0, 0.25, 0.5, 0.75, 1.0]
    walk_root = [euler_quat(15 * math.sin(2 * math.pi * t), 0, 0) for t in walk_t]
    walk_top = [euler_quat(0, 0, -25 * math.sin(2 * math.pi * t)) for t in walk_t]

    buf = bytearray()
    views = []
    accessors = []
    pos_v = _view(buf, views, pack_f(positions), 34962)
    pos_a = _accessor(accessors, pos_v, len(positions), 5126, "VEC3",
                      minmax=([min(p[i] for p in positions) for i in range(3)],
                              [max(p[i] for p in positions) for i in range(3)]))
    uv_v = _view(buf, views, pack_f(uvs), 34962)
    uv_a = _accessor(accessors, uv_v, len(uvs), 5126, "VEC2")
    jt_v = _view(buf, views, bytes(v for j in joints for v in j), 34962)
    jt_a = _accessor(accessors, jt_v, len(joints), 5121, "VEC4")
    wt_v = _view(buf, views, pack_f(weights), 34962)
    wt_a = _accessor(accessors, wt_v, len(weights), 5126, "VEC4")
    idx_v = _view(buf, views, struct.pack("<%dH" % len(indices), *indices), 34963)
    idx_a = _accessor(accessors, idx_v, len(indices), 5123, "SCALAR")
    ib_v = _view(buf, views, pack_f(sum(inv_bind, [])), None)
    ib_a = _accessor(accessors, ib_v, 2, 5126, "MAT4")
    png_v = _view(buf, views, png, None)

    anims = []
    for name, tracks in (
        ("Idle", [(1, "rotation", times, idle_rot)]),
        ("Walk", [(0, "rotation", walk_t, walk_root), (1, "rotation", walk_t, walk_top)]),
    ):
        samplers, channels = [], []
        for node, path_name, ts, vals in tracks:
            in_v = _view(buf, views, pack_f(ts), None)
            in_a = _accessor(accessors, in_v, len(ts), 5126, "SCALAR")
            out_v = _view(buf, views, pack_f([v for q in vals for v in q]), None)
            out_a = _accessor(accessors, out_v, len(vals), 5126, "VEC4")
            samplers.append({"input": in_a, "output": out_a, "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": path_name}})
        anims.append({"name": name, "samplers": samplers, "channels": channels})

    doc = {
        "asset": {"version": "2.0", "generator": "LuaStudio tools/gerar_assets3d.py"},
        "scene": 0,
        "scenes": [{"nodes": [0, 2]}],
        "nodes": [
            {"name": "Base", "children": [1], "rotation": [0, 0, 0, 1]},
            {"name": "Topo", "translation": [0, 1, 0]},
            {"name": "Malha", "mesh": 0, "skin": 0},
        ],
        "meshes": [{"name": "Tubo", "primitives": [{
            "attributes": {"POSITION": pos_a, "TEXCOORD_0": uv_a, "JOINTS_0": jt_a, "WEIGHTS_0": wt_a},
            "indices": idx_a, "material": 0}]}],
        "materials": [{"name": "Xadrez", "pbrMetallicRoughness": {
            "baseColorFactor": [1, 1, 1, 1], "baseColorTexture": {"index": 0}}}],
        "textures": [{"source": 0}],
        "images": [{"bufferView": png_v, "mimeType": "image/png"}],
        "skins": [{"joints": [0, 1], "inverseBindMatrices": ib_a}],
        "animations": anims,
        "accessors": accessors,
        "bufferViews": views,
        "buffers": [{"byteLength": len(buf)}],
    }
    json_bytes = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    while len(json_bytes) % 4:
        json_bytes += b" "
    while len(buf) % 4:
        buf.append(0)
    body = struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes
    body += struct.pack("<II", len(buf), 0x004E4942) + bytes(buf)
    with open(path, "wb") as handle:
        handle.write(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)


def euler_quat(x, y, z):
    def axis(angle, idx):
        h = math.radians(angle) * 0.5
        q = [0.0, 0.0, 0.0, math.cos(h)]
        q[idx] = math.sin(h)
        return q
    qx, qy, qz = axis(x, 0), axis(y, 1), axis(z, 2)
    def mul(a, b):
        ax, ay, az, aw = a
        bx, by, bz, bw = b
        return [aw * bx + ax * bw + ay * bz - az * by,
                aw * by - ax * bz + ay * bw + az * bx,
                aw * bz + ax * by - ay * bx + az * bw,
                aw * bw - ax * bx - ay * by - az * bz]
    return tuple(mul(qz, mul(qy, qx)))


def pack_f(values):
    flat = []
    for v in values:
        if isinstance(v, (tuple, list)):
            flat.extend(float(c) for c in v)
        else:
            flat.append(float(v))
    return struct.pack("<%df" % len(flat), *flat)


def make_obj(folder):
    with open(os.path.join(folder, "xadrez.png"), "wb") as handle:
        handle.write(make_png(64, 64, cell=8))
    mtl = "newmtl Xadrez\nKd 1.0 1.0 1.0\nmap_Kd xadrez.png\n\nnewmtl Azul\nKd 0.2 0.5 0.95\n"
    obj_lines = [
        "# caixa de teste com dois materiais",
        "mtllib caixa_textura.mtl",
        "v -1 0 -1", "v 1 0 -1", "v 1 0 1", "v -1 0 1",
        "v -1 2 -1", "v 1 2 -1", "v 1 2 1", "v -1 2 1",
        "vt 0 0", "vt 1 0", "vt 1 1", "vt 0 1",
        "usemtl Xadrez",
        "f 1/1 2/2 3/3 4/4",
        "f 5/1 8/4 7/3 6/2",
        "usemtl Azul",
        "f 1 5 6 2", "f 2 6 7 3", "f 3 7 8 4", "f 4 8 5 1",
    ]
    with open(os.path.join(folder, "caixa_textura.obj"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(obj_lines) + "\n")
    with open(os.path.join(folder, "caixa_textura.mtl"), "w", encoding="utf-8") as handle:
        handle.write(mtl)


def gerar(folder):
    os.makedirs(folder, exist_ok=True)
    make_glb(os.path.join(folder, "robo_animado.glb"))
    make_obj(folder)
    return sorted(os.listdir(folder))


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(here, "..", "examples", "assets3d")
    print("\n".join(gerar(os.path.normpath(target))))
