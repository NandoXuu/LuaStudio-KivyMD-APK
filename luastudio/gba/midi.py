# -*- coding: utf-8 -*-
"""MIDI (.mid) -> stream compacto .gbm para o PSG do GBA (2 pulse + wave + noise).

O player toca no ISR de VBlank (59,7275 Hz), custo de CPU quase zero e ROM minima.

Formato (bytes):
  [0..1] offset do loop (u16 LE, 0xFFFF = sem loop)   [2..3] reservado
  eventos:
    0x80|(n-1)   espera n frames (1..128)
    0x10|ch, nota, vb     note on  (ch 0=pulse1 1=pulse2 2=wave 3=noise)
                          vb = vol(0-15) | duty<<4 | decaimento<<6
                          no noise, 'nota' e o byte de parametros do ruido
    0x20|ch               note off
    0x01 fim   0x02 volta ao loop
"""
import struct

FPS = 59.7275
CH_PULSE1, CH_PULSE2, CH_WAVE, CH_NOISE = range(4)


class MidiError(Exception):
    pass


def _vlq(data, pos):
    v = 0
    while True:
        b = data[pos]
        pos += 1
        v = (v << 7) | (b & 0x7F)
        if not b & 0x80:
            return v, pos


def parse_midi(data):
    """Devolve (ppq, [(tick, ordem, canal, tipo, a, b)], tempos[(tick, us_por_beat)])."""
    if data[:4] != b"MThd":
        raise MidiError("arquivo nao e MIDI (falta MThd)")
    _hl, fmt, ntr, div = struct.unpack(">IHHH", data[4:14])
    if div & 0x8000:
        raise MidiError("MIDI com tempo SMPTE nao suportado")
    pos = 8 + _hl
    events, tempos, order = [], [(0, 500000)], 0
    for _t in range(ntr):
        if data[pos:pos + 4] != b"MTrk":
            raise MidiError("trilha invalida")
        ln = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        p, end, tick, run = pos + 8, pos + 8 + ln, 0, 0
        while p < end:
            dt, p = _vlq(data, p)
            tick += dt
            st = data[p]
            if st == 0xFF:
                typ = data[p + 1]
                l, p2 = _vlq(data, p + 2)
                if typ == 0x51 and l == 3:
                    tempos.append((tick, int.from_bytes(data[p2:p2 + 3], "big")))
                p = p2 + l
                continue
            if st in (0xF0, 0xF7):
                l, p = _vlq(data, p + 1)
                p += l
                continue
            if st & 0x80:
                run = st
                p += 1
            st = run
            kind, ch = st >> 4, st & 15
            n = 1 if kind in (0xC, 0xD) else 2
            a = data[p]
            b = data[p + 1] if n == 2 else 0
            p += n
            if kind in (0x8, 0x9, 0xB, 0xC):
                if kind == 0x9 and b == 0:
                    kind = 0x8
                events.append((tick, order, ch, kind, a, b))
                order += 1
        pos = end
    events.sort(key=lambda e: (e[0], e[1]))
    tempos = sorted(set(tempos))
    return div, events, tempos


def _tick_to_sec(tick, ppq, tempos):
    sec, last_t, last_us = 0.0, 0, tempos[0][1]
    for t, us in tempos:
        if t >= tick:
            break
        sec += (t - last_t) * last_us / 1e6 / ppq
        last_t, last_us = t, us
    return sec + (tick - last_t) * last_us / 1e6 / ppq


def _noise_param(note):
    """Mapeia notas de percussao GM para parametros do ruido do GBA (s<<4 | largura<<3 | r)."""
    if note in (35, 36):                      # bumbo: grave e longo
        return (0xB << 4) | 3, 2
    if note in (38, 40, 37, 39):              # caixa/clap
        return (0x6 << 4) | 1, 1
    if note in (42, 44, 46, 69, 70, 82):      # chimbal: agudo e curto
        return (0x2 << 4) | 0x8 | 1, 3
    return (0x4 << 4) | 2, 1                  # demais


def convert(data, max_seconds=None, loop=True, channel_map=None, volume_scale=1.0):
    """Converte bytes de um .mid em bytes .gbm. Voz mais aguda ganha pulse1; depois pulse2/wave."""
    ppq, events, tempos = parse_midi(data)
    drums = [e for e in events if e[2] == 9]
    # escolhe ate 3 canais melodicos pelos mais usados (por numero de notas)
    count = {}
    for e in events:
        if e[3] == 0x9 and e[2] != 9:
            count[e[2]] = count.get(e[2], 0) + 1
    chosen = sorted(count, key=lambda c: -count[c])[:3]
    if channel_map is None:
        channel_map = {}
        # baixo (nota media mais grave) vai para a onda; resto para os pulses
        avg = {}
        for e in events:
            if e[3] == 0x9 and e[2] in chosen:
                avg.setdefault(e[2], []).append(e[4])
        order = sorted(chosen, key=lambda c: sum(avg[c]) / len(avg[c]))
        slots = [CH_WAVE, CH_PULSE2, CH_PULSE1]
        for c, s in zip(order, slots):
            channel_map[c] = s
        if len(order) == 2:
            channel_map[order[0]], channel_map[order[1]] = CH_WAVE, CH_PULSE1
        if len(order) == 1:
            channel_map[order[0]] = CH_PULSE1
    prog = {}
    active = {}             # canal gba -> (midi_ch, nota)
    out = []                # (frame, ordem, bytes)
    last_frame = 0
    seq = 0

    def emit(fr, b):
        nonlocal seq
        out.append((fr, seq, bytes(b)))
        seq += 1

    for tick, _o, ch, kind, a, b in events:
        sec = _tick_to_sec(tick, ppq, tempos)
        if max_seconds and sec > max_seconds:
            break
        fr = int(round(sec * FPS))
        last_frame = max(last_frame, fr)
        if kind == 0xC:
            prog[ch] = a
        elif kind == 0x9:
            vol = max(1, min(15, int(round(b / 127.0 * 15 * volume_scale))))
            if ch == 9:
                param, dec = _noise_param(a)
                emit(fr, [0x10 | CH_NOISE, param, vol | (dec << 6)])
                active[CH_NOISE] = (9, a)
            elif ch in channel_map:
                g = channel_map[ch]
                note = a
                lo = 36 if g != CH_WAVE else 24
                while note < lo:
                    note += 12
                while note > 119:
                    note -= 12
                p = prog.get(ch, 0)
                dec = 2 if (p // 8) in (3, 4, 5, 6, 12, 13) else 0   # guitarra/piano/percussivos decaem
                duty = 2 if g == CH_PULSE1 else 1
                emit(fr, [0x10 | g, note, vol | (duty << 4) | (dec << 6)])
                active[g] = (ch, a)
        elif kind == 0x8:
            if ch == 9:
                continue        # ruido tem envelope proprio
            g = channel_map.get(ch)
            if g is not None and active.get(g, (None, None)) == (ch, a):
                emit(fr, [0x20 | g])
                active.pop(g, None)
    out.sort(key=lambda e: (e[0], e[1]))
    end_frame = last_frame + 1
    stream = bytearray(b"\x00\x00\x00\x00")
    cur = 0
    loop_off = 0xFFFF
    if loop:
        loop_off = 4
    for fr, _s, b in out:
        gap = fr - cur
        while gap > 0:
            n = min(gap, 128)
            stream.append(0x80 | (n - 1))
            gap -= n
            cur += n
        stream += b
    gap = end_frame - cur
    while gap > 0:
        n = min(gap, 128)
        stream.append(0x80 | (n - 1))
        gap -= n
    stream.append(0x02 if loop else 0x01)
    stream[0:2] = struct.pack("<H", loop_off)
    return bytes(stream), {"frames": end_frame, "seconds": end_frame / FPS,
                           "bytes": len(stream), "channels": dict(channel_map)}


def to_c(name, stream):
    body = ",".join("0x%02X" % b for b in stream)
    return "const u8 %s[%d] ALIGN4 = {%s};\n" % (name, len(stream), body)
