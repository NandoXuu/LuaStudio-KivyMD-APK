# -*- coding: utf-8 -*-
"""Testes do modulo GBA. Roda no PC: python -m unittest luastudio.gba.tests.test_gba"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GBA = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(GBA)))

from luastudio.gba import assets, datagen, midi  # noqa: E402

RT = os.path.join(GBA, "runtime")


def make_midi(notes, ppq=96, tempo=500000):
    """notes: [(tick_on, tick_off, canal, nota, vel)] -> bytes SMF formato 0."""
    ev = []
    for on, off, ch, n, v in notes:
        ev.append((on, 0x90 | ch, n, v))
        ev.append((off, 0x80 | ch, n, 0))
    ev.sort()
    trk = b"\x00\xFF\x51\x03" + tempo.to_bytes(3, "big")
    last = 0
    for t, st, a, b in ev:
        d, last = t - last, t
        vl = bytearray([d & 0x7F])
        d >>= 7
        while d:
            vl.insert(0, (d & 0x7F) | 0x80)
            d >>= 7
        trk += bytes(vl) + bytes([st, a, b])
    trk += b"\x00\xFF\x2F\x00"
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, ppq) + b"MTrk" + struct.pack(">I", len(trk)) + trk


class HostBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("gcc"):
            raise unittest.SkipTest("gcc ausente")
        cls.tmp = tempfile.mkdtemp()
        song, _ = midi.convert(make_midi([(0, 96, 0, 69, 100), (96, 192, 0, 81, 100), (0, 192, 1, 57, 90),
                                          (0, 48, 9, 36, 100)]), loop=False)
        raw = bytes((i * 7 + (i // 5)) & 0xFF for i in range(300)) + b"abcabcabcabcabcabc" * 20
        lz = assets.lz77_compress(raw)
        cls.raw = raw
        with open(os.path.join(cls.tmp, "data.c"), "w") as f:
            f.write('#include "gba.h"\n' + midi.to_c("test_song", song) + midi.to_c("test_lz", lz)
                    + "const unsigned test_lz_size = %d;\n" % len(raw))
            f.write(datagen.generate_data_c().replace('#include "gba.h"', ""))
        cls.exe = os.path.join(cls.tmp, "host")
        cmd = ["gcc", "-O1", "-DGBA_HOST", "-Wall", "-Wno-pointer-to-int-cast", "-I", RT,
               os.path.join(RT, "gba_rt.c"), os.path.join(cls.tmp, "data.c"),
               os.path.join(HERE, "host_test.c"), "-o", cls.exe]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stderr)
        cls.warn = r.stderr

    def run_host(self, arg):
        r = subprocess.run([self.exe, arg], cwd=self.tmp, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_no_warnings(self):
        self.assertEqual(self.warn.strip(), "")

    def _vram(self, mode):
        self.run_host("gfx%d" % mode)
        d = open(os.path.join(self.tmp, "vram.bin"), "rb").read()
        if mode == 3:
            return [[struct.unpack_from("<H", d, (y * 240 + x) * 2)[0] for x in range(240)] for y in range(160)]
        return [[d[y * 240 + x] for x in range(240)] for y in range(160)]

    def test_draw_mode3_and_4(self):
        for mode, (W, R, G, B, Y) in ((3, (0x7FFF, 0x1F, 0x3E0, 0x7C00, 0x3FF)), (4, (1, 2, 3, 4, 5))):
            v = self._vram(mode)
            self.assertEqual(v[15][15], R, mode)            # fill com x impar
            self.assertEqual(v[10][10], R)
            self.assertEqual(v[30][50], R)
            self.assertEqual(v[31][50], 0 if mode == 4 else 0)   # fora do retangulo (y=30 e ultimo)
            self.assertEqual(v[45][11], G)                  # fill x=11 impar, largura 40
            self.assertEqual(v[45][50], G)
            self.assertNotEqual(v[45][51], G)               # nao vaza uma coluna
            self.assertEqual(v[5][0], G)                    # hline recortada
            self.assertEqual(v[5][239], G)
            self.assertEqual(v[0][5], G)                    # vline recortada
            self.assertEqual(v[159][5], G)
            self.assertEqual(v[10][100], W)                 # contorno
            self.assertEqual(v[30][130], W)
            self.assertEqual(v[100][150], W)                # circulo (cx-r)
            self.assertEqual(v[110][60], R)                 # circulo cheio
            self.assertEqual(v[100][210], W)
            self.assertEqual(v[80][100], 0)
            diag = [v[int(x * 159 / 239)][x] for x in range(0, 240, 40)]
            self.assertIn(B, diag)                          # linha azul presente
            # blit com transparencia: pixel (0,0) do sprite (idx 0) nao desenha, deixa fundo
            self.assertEqual(v[20][200], 0)
            self.assertNotEqual(v[20][201], 0)
            self.assertNotEqual(v[21][233], 0)               # blit recortado a direita
            self.assertNotEqual(v[160 - 5][0], 0)            # recortado a esquerda
            # texto: algum pixel branco na area do texto
            self.assertTrue(any(v[y][x] == W for y in range(80, 88) for x in range(8, 140)))
            self.assertTrue(any(v[y][x] == B for y in range(92, 100) for x in range(9, 70)))  # fundo do texto

    def test_modes_equal(self):
        a, b = self._vram(3), self._vram(4)
        names3 = {0: 0, 0x7FFF: 1, 0x1F: 2, 0x3E0: 3, 0x7C00: 4, 0x3FF: 5}
        diff = 0
        for y in range(160):
            for x in range(240):
                p3, p4 = a[y][x], b[y][x]
                if p3 in names3 and names3[p3] != p4 and p4 in (0, 1, 2, 3, 4, 5):
                    diff += 1
        self.assertEqual(diff, 0)

    def test_math(self):
        out = self.run_host("math").decode().split("\n")
        self.assertEqual(out[0], "0 -70000 2147483647 1000 1")
        self.assertEqual(out[1], "256 256")

    def test_lz77_roundtrip(self):
        self.assertEqual(assets.lz77_decompress(assets.lz77_compress(self.raw)), self.raw)
        self.assertEqual(self.run_host("lz"), self.raw)
        self.assertLess(len(assets.lz77_compress(self.raw)), len(self.raw))

    def test_music_engine(self):
        self.run_host("snd")
        rows = [l.split() for l in open(os.path.join(self.tmp, "snd.log")).read().strip().split("\n")[:-1]]
        pulse, _ = datagen.note_tables()
        x1 = [int(r[1]) for r in rows]
        self.assertIn(pulse[69], x1)            # A4 tocou no pulse 1
        self.assertIn(pulse[81], x1)            # A5 depois
        self.assertLess(x1.index(pulse[69]), x1.index(pulse[81]))
        self.assertEqual(open(os.path.join(self.tmp, "snd.log")).read().strip().split("\n")[-1], "playing=0")
        # 192 ticks a 500000us/beat, ppq 96 = 1s = ~60 frames
        self.assertTrue(55 <= len(rows) <= 70, len(rows))


class MidiAssets(unittest.TestCase):
    def test_convert_and_format(self):
        data = make_midi([(0, 96, 0, 60, 100), (96, 192, 0, 64, 100)])
        stream, info = midi.convert(data, loop=True)
        self.assertEqual(struct.unpack("<H", stream[:2])[0], 4)
        self.assertEqual(stream[-1], 2)
        self.assertAlmostEqual(info["seconds"], 1.0, delta=0.1)
        self.assertEqual(stream[4], 0x10 | midi.CH_PULSE1)

    def test_bad_midi(self):
        with self.assertRaises(midi.MidiError):
            midi.convert(b"nope")

    def test_note_tables(self):
        p, w = datagen.note_tables()
        f = 131072.0 / (2048 - p[69])
        self.assertAlmostEqual(f, 440.0, delta=1.5)
        self.assertAlmostEqual(65536.0 / (2048 - w[69]), 440.0, delta=1.5)

    def test_image_assets(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow ausente")
        d = tempfile.mkdtemp()
        im = Image.new("RGBA", (32, 16), (0, 0, 0, 0))
        for x in range(16):
            for y in range(16):
                im.putpixel((x, y), (255, 0, 0, 255))
        im.save(os.path.join(d, "spr_hero_16x16.png"))
        Image.new("RGBA", (64, 32), (10, 200, 30, 255)).save(os.path.join(d, "bg_grass.png"))
        Image.new("RGB", (40, 30), (255, 255, 0)).save(os.path.join(d, "img_title.png"))
        h, c, rep = assets.build_assets(d, mode=4)
        self.assertIn("HERO_FRAMES 2", h)
        self.assertIn("GRASS_TILE_COUNT 1", h)         # tiles iguais deduplicados
        self.assertIn("title_img", h)
        self.assertEqual(len(rep), 3)
        h3, _c3, _ = assets.build_assets(d, mode=3)
        self.assertIn("u16 title_img", h3)



class Pipeline(unittest.TestCase):
    SIZE_OUT = (".text 4096 134217728\n.iwram 1200 50331648\n.ewram 0 33554432\n"
                ".sbss 2048 33554432\n.bss 800 50331648\n")

    def setUp(self):
        from luastudio.gba import toolchain
        self.tc = toolchain
        self.dir = tempfile.mkdtemp()
        toolchain.create_project(self.dir, "blank", title="TESTE")
        self.calls = []
        self.tools = {"gcc": "gcc", "objcopy": "objcopy", "size": "size", "bin": self.dir}

    def runner(self, cmd):
        self.calls.append(cmd)
        if cmd[0] == "objcopy":
            open(cmd[-1], "wb").write(b"\x00\x00\x00\xEA" + b"\x00" * 0x2FC)
            return 0, ""
        if cmd[0] == "size":
            return 0, self.SIZE_OUT
        out = cmd[cmd.index("-o") + 1]
        if "-c" in cmd:
            src = cmd[cmd.index("-c") + 1]
            if src.endswith(".c") and b"BOOM" in open(src, "rb").read():
                return 1, "%s:3:5: error: unknown type name 'BOOM'\n" % src
        open(out, "wb").write(b"x")
        return 0, ""

    def test_build_ok_and_cache(self):
        r = self.tc.build(self.dir, tools=self.tools, runner=self.runner)
        self.assertTrue(r.ok, r.log)
        rom = open(r.rom, "rb").read()
        self.assertEqual(rom[0xA0:0xA5], b"TESTE")
        self.assertEqual(rom[0xB2], 0x96)
        self.assertEqual((sum(rom[0xA0:0xBE]) + 0x19) & 0xFF, 0)        # checksum valido
        self.assertEqual(r.sizes["iwram"], 2000)
        self.assertEqual(r.sizes["ewram"], 2048)
        n1 = len([c for c in self.calls if "-c" in c])
        self.calls[:] = []
        r2 = self.tc.build(self.dir, tools=self.tools, runner=self.runner)
        self.assertTrue(r2.ok)
        n2 = len([c for c in self.calls if "-c" in c])
        self.assertEqual(n2, 1)                                          # so o crt0 (sem cache)
        self.assertGreater(n1, n2)
        flags = [c for c in self.calls if "-c" in c][0]
        self.assertIn("-mcpu=arm7tdmi", " ".join(self.calls[-3]))

    def test_incremental_recompiles_changed_file(self):
        self.tc.build(self.dir, tools=self.tools, runner=self.runner)
        self.calls[:] = []
        with open(os.path.join(self.dir, "src", "main.c"), "a") as f:
            f.write("\n/* mudou */\n")
        self.tc.build(self.dir, tools=self.tools, runner=self.runner)
        compiled = [c[c.index("-c") + 1] for c in self.calls if "-c" in c and c[c.index("-c") + 1].endswith(".c")]
        self.assertEqual([os.path.basename(c) for c in compiled], ["main.c"])

    def test_compile_error_parsed(self):
        with open(os.path.join(self.dir, "src", "main.c"), "a") as f:
            f.write("\nBOOM x;\n")
        r = self.tc.build(self.dir, tools=self.tools, runner=self.runner)
        self.assertFalse(r.ok)
        e = r.errors()[0]
        self.assertEqual((e[1], e[2]), (3, 5))
        self.assertIn("BOOM", e[4])

    def test_limits_are_advisory_and_build_continues(self):
        with open(os.path.join(self.dir, "src", "main.c"), "w") as f:
            f.write('#include <stdio.h>\n#include "gba.h"\nint main(void){ float a = 1.5f; printf("x"); malloc(4);\n'
                    "u8 big[4096]; int d = a / a; while(1){} }\n")
        r = self.tc.build(self.dir, tools=self.tools, runner=self.runner)
        self.assertTrue(r.ok)
        self.assertTrue(self.calls)                                    # compilador foi chamado apesar dos avisos
        codes = " ".join(d[4] for d in r.warnings())
        for c in ("GBA001", "GBA002", "GBA003", "GBA004"):
            self.assertIn(c, codes)

    def test_limits_allow_good_code(self):
        from luastudio.gba import limits
        good = ('#include "gba.h"\n/* float printf malloc em comentario */\nconst char *s = "float malloc(1)";\n'
                "int f(int a){ return a / 8 + a % 16 + a / 10; }\nvoid g(void){ static u8 big[4096]; (void)big; }\n")
        self.assertEqual(limits.check_source("a.c", good), [])
        bad = "int f(int a, int b){ return a / b; }\n"
        self.assertEqual([i.code for i in limits.check_source("a.c", bad)], ["GBA006"])
        self.assertEqual([i.severity for i in limits.check_source("a.c", "float x;", allow_float=True)], ["warning"])

    def test_missing_toolchain(self):
        old = self.tc.find_toolchain
        self.tc.find_toolchain = lambda c="": None
        try:
            with self.assertRaises(self.tc.BuildError):
                self.tc.build(self.dir, runner=self.runner)
        finally:
            self.tc.find_toolchain = old

    def test_assets_in_build(self):
        from PIL import Image
        Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(os.path.join(self.dir, "assets", "spr_a_16x16.png"))
        open(os.path.join(self.dir, "assets", "tema.mid"), "wb").write(make_midi([(0, 96, 0, 60, 100)]))
        r = self.tc.build(self.dir, tools=self.tools, runner=self.runner)
        self.assertTrue(r.ok, r.log)
        h = open(os.path.join(self.dir, "build", "assets.h")).read()
        self.assertIn("song_tema", h)
        self.assertIn("a_tiles", h)

    def test_gcc_diag_parser(self):
        d = self.tc.parse_gcc_output("src/main.c:12:7: warning: unused variable 'x'\n"
                                     "main.o:(.text+0x4): undefined reference to `foo'\n")
        self.assertEqual(d[0], ("src/main.c", 12, 7, "warning", "unused variable 'x'"))
        self.assertEqual(d[1][3], "error")

    def test_templates_compile_against_api(self):
        if not shutil.which("gcc"):
            self.skipTest("gcc ausente")
        for name, code in self.tc.TEMPLATES.items():
            d = tempfile.mkdtemp()
            p = os.path.join(d, "t.c")
            open(p, "w").write(code)
            r = subprocess.run(["gcc", "-fsyntax-only", "-Wall", "-Wextra", "-DGBA_HOST", "-I", RT, p],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, name + r.stderr)
            self.assertEqual(r.stderr.strip(), "", name + r.stderr)


if __name__ == "__main__":
    unittest.main()
