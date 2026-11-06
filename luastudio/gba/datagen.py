# -*- coding: utf-8 -*-
"""Gera gba_data.c: fonte, LUT de seno e tabelas de frequencia (MIDI -> registradores PSG)."""
import math

from . import fontdata


def note_tables():
    pulse, wave = [], []
    for n in range(128):
        f = 440.0 * 2 ** ((n - 69) / 12.0)
        xp = int(round(2048 - 131072.0 / f))
        xw = int(round(2048 - 65536.0 / f))
        pulse.append(max(0, min(2047, xp)))
        wave.append(max(0, min(2047, xw)))
    return pulse, wave


def _arr(vals, per=12):
    lines = []
    for i in range(0, len(vals), per):
        lines.append("    " + ", ".join(str(v) for v in vals[i:i + per]) + ",")
    return "\n".join(lines)


def generate_data_c():
    font = fontdata.glyph_rows()
    sin = [int(round(math.sin(2 * math.pi * i / 256) * 256)) for i in range(256)]
    pulse, wave = note_tables()
    out = ["/* gerado por luastudio.gba.datagen - nao edite */", '#include "gba.h"', ""]
    out.append("const u8 gba_font[95][8] = {")
    for g in font:
        out.append("    {" + ",".join("0x%02X" % r for r in g) + "},")
    out.append("};")
    out.append("const s16 gba_sin_lut[256] = {\n%s\n};" % _arr(sin, 16))
    out.append("const u16 gba_note_pulse[128] = {\n%s\n};" % _arr(pulse))
    out.append("const u16 gba_note_wave[128] = {\n%s\n};" % _arr(wave))
    return "\n".join(out) + "\n"
