# -*- coding: utf-8 -*-
"""Conversao de assets para dados C do GBA (PNG -> tiles/bitmap, WAV -> PCM 8 bit, MID -> .gbm).

Convencao de nomes na pasta assets/ do projeto:
  spr_<nome>_<W>x<H>.png   sprite sheet 4bpp, quadros WxH (8,16,32,64)  -> <nome>_pal/_tiles
  bg_<nome>.png            tileset+mapa 4bpp com tiles duplicados removidos -> <nome>_tiles/_map
  img_<nome>.png | outros  bitmap de tela cheia (modo 3: 15 bits, modo 4: paleta 256)
  <nome>.wav               efeito PCM 8-bit mono                          -> sfx_<nome>
  <nome>.mid               musica PSG compacta                            -> song_<nome>
Sufixo _lz no nome gera dados comprimidos em LZ77 (use lz77_decompress em RAM).
"""
import os
import re
import wave

from . import midi as midimod


class AssetError(Exception):
    pass


def _ident(name):
    s = re.sub(r"[^0-9a-zA-Z_]", "_", name)
    if not s or s[0].isdigit():
        s = "a_" + s
    return s


def rgb15(r, g, b):
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


def _fmt(vals, per, width):
    fmt = "0x%0" + str(width) + "X"
    rows = []
    for i in range(0, len(vals), per):
        rows.append("    " + ",".join(fmt % v for v in vals[i:i + per]) + ",")
    return "\n".join(rows)


# ------------------------------------------------------------------ LZ77
def lz77_compress(data):
    """LZ77 tipo 0x10 do BIOS do GBA (janela 4096, copias de 3..18 bytes)."""
    data = bytes(data)
    n = len(data)
    out = bytearray([0x10, n & 255, (n >> 8) & 255, (n >> 16) & 255])
    table = {}
    i = 0
    while i < n:
        flags, block = 0, bytearray()
        for bit in range(8):
            if i >= n:
                break
            best_len, best_disp = 0, 0
            if i + 3 <= n:
                key = data[i:i + 3]
                for j in reversed(table.get(key, [])[-32:]):
                    if i - j > 4096:
                        break
                    l = 3
                    while l < 18 and i + l < n and data[j + l] == data[i + l]:
                        l += 1
                    if l > best_len:
                        best_len, best_disp = l, i - j
                        if l == 18:
                            break
            step = best_len if best_len >= 3 else 1
            if best_len >= 3:
                flags |= 0x80 >> bit
                d = best_disp - 1
                block.append(((best_len - 3) << 4) | (d >> 8))
                block.append(d & 255)
            else:
                block.append(data[i])
            for k in range(i, min(i + step, n - 2)):
                table.setdefault(data[k:k + 3], []).append(k)
            i += step
        out.append(flags)
        out += block
    while len(out) % 4:
        out.append(0)
    return bytes(out)


def lz77_decompress(buf):
    size = buf[1] | (buf[2] << 8) | (buf[3] << 16)
    out, p = bytearray(), 4
    while len(out) < size:
        fl = buf[p]
        p += 1
        for b in range(8):
            if len(out) >= size:
                break
            if fl & (0x80 >> b):
                ln = (buf[p] >> 4) + 3
                disp = (((buf[p] & 15) << 8) | buf[p + 1]) + 1
                p += 2
                for _ in range(ln):
                    out.append(out[-disp])
            else:
                out.append(buf[p])
                p += 1
    return bytes(out[:size])


# ----------------------------------------------------------------- imagens
def _pixels(img):
    f = getattr(img, "get_flattened_data", None)
    return list(f()) if f else list(img.getdata())


def _open(path):
    from PIL import Image
    return Image.open(path).convert("RGBA")


def _quantize(img, colors, transparent_zero):
    """Devolve (indices[w*h], paleta15[]). Com transparent_zero o indice 0 e reservado."""
    from PIL import Image
    w, h = img.size
    px = _pixels(img)
    rgb = Image.new("RGB", (w, h))
    rgb.putdata([(r, g, b) for r, g, b, _a in px])
    avail = colors - (1 if transparent_zero else 0)
    q = rgb.quantize(colors=avail, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = q.getpalette() or []
    idx = _pixels(q)
    shift = 1 if transparent_zero else 0
    out = []
    for i, (_r, _g, _b, a) in enumerate(px):
        out.append(0 if (transparent_zero and a < 128) else idx[i] + shift)
    used = max(out) + 1 if out else 1
    pal15 = [0] * max(colors if transparent_zero else used, used)
    for k in range(avail):
        if k * 3 + 2 < len(pal):
            pal15[k + shift] = rgb15(pal[k * 3], pal[k * 3 + 1], pal[k * 3 + 2])
    return out, pal15[:colors]


def _tile4(idx, stride, x0, y0):
    words = []
    for y in range(8):
        v = 0
        for x in range(8):
            v |= (idx[(y0 + y) * stride + x0 + x] & 15) << (4 * x)
        words.append(v)
    return tuple(words)


def convert_sprite_sheet(path, name, fw, fh):
    if fw % 8 or fh % 8:
        raise AssetError("%s: quadro %dx%d precisa ser multiplo de 8" % (os.path.basename(path), fw, fh))
    img = _open(path)
    w, h = img.size
    if w % fw or h % fh:
        raise AssetError("%s: imagem %dx%d nao divide em quadros %dx%d" % (os.path.basename(path), w, h, fw, fh))
    idx, pal = _quantize(img, 16, True)
    words = []
    frames = 0
    for fy in range(0, h, fh):
        for fx in range(0, w, fw):
            for ty in range(0, fh, 8):          # 1D mapping: tiles do quadro em ordem de linha
                for tx in range(0, fw, 8):
                    words += _tile4(idx, w, fx + tx, fy + ty)
            frames += 1
    pal += [0] * (16 - len(pal))
    tiles_per_frame = (fw // 8) * (fh // 8)
    h_txt = ("#define %s_FRAMES %d\n#define %s_TILES_PER_FRAME %d\n#define %s_W %d\n#define %s_H %d\n"
             "extern const u16 %s_pal[16];\nextern const u32 %s_tiles[%d];\n"
             % (name.upper(), frames, name.upper(), tiles_per_frame, name.upper(), fw, name.upper(), fh,
                name, name, len(words)))
    c_txt = ("const u16 %s_pal[16] ALIGN4 = {%s};\nconst u32 %s_tiles[%d] ALIGN4 = {\n%s\n};\n"
             % (name, ",".join("0x%04X" % p for p in pal), name, len(words), _fmt(words, 8, 8)))
    return h_txt, c_txt, {"bytes": len(words) * 4 + 32, "frames": frames}


def convert_tileset(path, name):
    img = _open(path)
    w, h = img.size
    if w % 8 or h % 8:
        raise AssetError("%s: tamanho deve ser multiplo de 8" % os.path.basename(path))
    idx, pal = _quantize(img, 16, False)
    pal += [0] * (16 - len(pal))
    uniq, order, tmap = [], {}, []
    for ty in range(0, h, 8):
        for tx in range(0, w, 8):
            t = _tile4(idx, w, tx, ty)
            if t not in order:
                order[t] = len(uniq)
                uniq.append(t)
            tmap.append(order[t])
    if len(uniq) > 1024:
        raise AssetError("%s: %d tiles unicos (maximo 1024)" % (os.path.basename(path), len(uniq)))
    words = [x for t in uniq for x in t]
    h_txt = ("#define %s_TILE_COUNT %d\n#define %s_MAP_W %d\n#define %s_MAP_H %d\n"
             "extern const u16 %s_pal[16];\nextern const u32 %s_tiles[%d];\nextern const u16 %s_map[%d];\n"
             % (name.upper(), len(uniq), name.upper(), w // 8, name.upper(), h // 8,
                name, name, len(words), name, len(tmap)))
    c_txt = ("const u16 %s_pal[16] ALIGN4 = {%s};\nconst u32 %s_tiles[%d] ALIGN4 = {\n%s\n};\n"
             "const u16 %s_map[%d] ALIGN4 = {\n%s\n};\n"
             % (name, ",".join("0x%04X" % p for p in pal), name, len(words), _fmt(words, 8, 8),
                name, len(tmap), _fmt(tmap, 16, 4)))
    return h_txt, c_txt, {"bytes": len(words) * 4 + len(tmap) * 2 + 32, "tiles": len(uniq)}


def convert_bitmap(path, name, mode):
    img = _open(path)
    w, h = img.size
    if w > 240 or h > 160:
        raise AssetError("%s: %dx%d maior que a tela 240x160" % (os.path.basename(path), w, h))
    if mode == 3:
        vals = [rgb15(r, g, b) for r, g, b, _a in _pixels(img)]
        h_txt = "#define %s_W %d\n#define %s_H %d\nextern const u16 %s_img[%d];\n" % (
            name.upper(), w, name.upper(), h, name, len(vals))
        c_txt = "const u16 %s_img[%d] ALIGN4 = {\n%s\n};\n" % (name, len(vals), _fmt(vals, 12, 4))
        return h_txt, c_txt, {"bytes": len(vals) * 2}
    idx, pal = _quantize(img, 256, False)
    pad = (-len(idx)) % 4
    data = idx + [0] * pad
    pal += [0] * (256 - len(pal))
    h_txt = ("#define %s_W %d\n#define %s_H %d\nextern const u16 %s_pal[256];\nextern const u8 %s_img[%d];\n"
             % (name.upper(), w, name.upper(), h, name, name, len(data)))
    c_txt = ("const u16 %s_pal[256] ALIGN4 = {\n%s\n};\nconst u8 %s_img[%d] ALIGN4 = {\n%s\n};\n"
             % (name, _fmt(pal, 12, 4), name, len(data), _fmt(data, 24, 2)))
    return h_txt, c_txt, {"bytes": len(data) + 512}


# --------------------------------------------------------------------- audio
def wav_to_pcm8(path, hz=11025):
    with wave.open(path, "rb") as w:
        ch, sw, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw not in (1, 2):
        raise AssetError("%s: WAV precisa ser 8 ou 16 bits" % os.path.basename(path))
    samples = []
    step = sw * ch
    for i in range(0, len(raw) - step + 1, step):
        acc = 0
        for c in range(ch):
            o = i + c * sw
            acc += (raw[o] - 128) * 256 if sw == 1 else int.from_bytes(raw[o:o + 2], "little", signed=True)
        samples.append(acc / ch)
    out_n = max(1, int(len(samples) * hz / float(rate)))
    out = []
    for k in range(out_n):
        pos = k * rate / float(hz)
        i = int(pos)
        f = pos - i
        a = samples[min(i, len(samples) - 1)]
        b = samples[min(i + 1, len(samples) - 1)]
        v = int(round((a + (b - a) * f) / 256.0))
        out.append(max(-128, min(127, v)) & 255)
    out += [0] * ((-len(out)) % 4)
    return out, hz


def convert_wav(path, name, hz=11025):
    data, hz = wav_to_pcm8(path, hz)
    h_txt = "#define %s_HZ %d\n#define %s_LEN %d\nextern const s8 %s[%d];\n" % (
        name.upper(), hz, name.upper(), len(data), name, len(data))
    c_txt = "const s8 %s[%d] ALIGN4 = {\n%s\n};\n" % (name, len(data), ",\n".join(
        "    " + ",".join(str(v - 256 if v > 127 else v) for v in data[i:i + 24]) for i in range(0, len(data), 24)))
    return h_txt, c_txt, {"bytes": len(data)}


def convert_midi(path, name, loop=True, max_seconds=None):
    with open(path, "rb") as fh:
        stream, info = midimod.convert(fh.read(), max_seconds=max_seconds, loop=loop)
    h_txt = "extern const u8 %s[%d];\n" % (name, len(stream))
    return h_txt, midimod.to_c(name, stream), {"bytes": len(stream), "seconds": round(info["seconds"], 1)}


# ------------------------------------------------------------------ pasta
def build_assets(asset_dir, mode=3):
    """Converte tudo de asset_dir. Devolve (assets.h, assets.c, relatorio[(arquivo, info)])."""
    hs = ['#include "gba.h"', ""]
    cs = ['#include "gba.h"', '#include "assets.h"', ""]
    report = []
    if not os.path.isdir(asset_dir):
        return "\n".join(hs) + "\n", "\n".join(cs) + "\n", report
    for fn in sorted(os.listdir(asset_dir)):
        stem, ext = os.path.splitext(fn)
        ext = ext.lower()
        path = os.path.join(asset_dir, fn)
        try:
            if ext == ".png":
                m = re.match(r"^spr_(.+?)_(\d+)x(\d+)$", stem)
                if m:
                    res = convert_sprite_sheet(path, _ident(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif stem.startswith("bg_"):
                    res = convert_tileset(path, _ident(stem[3:]))
                else:
                    res = convert_bitmap(path, _ident(stem[4:] if stem.startswith("img_") else stem), mode)
            elif ext == ".wav":
                res = convert_wav(path, "sfx_" + _ident(stem))
            elif ext in (".mid", ".midi"):
                res = convert_midi(path, "song_" + _ident(stem))
            else:
                continue
        except AssetError:
            raise
        except Exception as ex:
            raise AssetError("%s: %s" % (fn, ex))
        hs.append(res[0])
        cs.append(res[1])
        report.append((fn, res[2]))
    return "\n".join(hs) + "\n", "\n".join(cs) + "\n", report
