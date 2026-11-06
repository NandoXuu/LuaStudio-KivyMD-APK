# -*- coding: utf-8 -*-
"""Projeto GBA + pipeline de build: C -> (arm-none-eabi-gcc) -> .elf -> .gba.

O Python orquestra tudo por baixo dos panos: valida limites, converte assets,
gera tabelas, compila (com cache incremental), liga, gera a ROM e relata memoria.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

from . import assets as assetmod
from . import datagen, gbafix, limits

RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")
CONFIG_NAME = "gba_project.json"

DEFAULT_CONFIG = {
    "title": "MEU JOGO", "game_code": "AGBE", "maker": "01", "version": 0,
    "mode": 3,                  # 3 / 4 (bitmap) ou 0 (tiles): informa a conversao de assets
    "opt": "-O2",               # -O2 | -O3 | -Os
    "lto": False,
    "allow_float": False,       # False = float/double viram erro
    "warn_division": True,
    "thumb": True,              # codigo da ROM em Thumb (menor/mais rapido em ROM de 16 bits)
    "extra_cflags": "",
    "toolchain_dir": "",        # pasta bin/ do arm-none-eabi-gcc (opcional)
    "emulator": "",             # caminho do mGBA/VBA para o botao Rodar
    "bridge_enabled": True,      # usa a ponte Termux/Debian quando o GCC nao existe no Pydroid
    "bridge_url": "http://127.0.0.1:8765",
}

GCC_NAMES = ["arm-none-eabi-gcc", "arm-none-eabi-gcc.exe"]


class BuildError(Exception):
    pass


# --------------------------------------------------------------- toolchain
def toolchain_search_dirs(configured=""):
    dirs = []
    if configured:
        dirs.append(configured)
    for env in ("DEVKITARM", "GBA_TOOLCHAIN"):
        v = os.environ.get(env)
        if v:
            dirs += [os.path.join(v, "bin"), v]
    dirs += ["/opt/devkitpro/devkitARM/bin", "C:\\devkitPro\\devkitARM\\bin",
             "/usr/local/bin", "/usr/bin", os.path.expanduser("~/.luastudio/gba/toolchain/bin"),
             "/data/data/com.termux/files/usr/bin"]
    return dirs


def find_toolchain(configured=""):
    """Devolve dict(gcc, objcopy, size, prefix_dir) ou None."""
    for d in toolchain_search_dirs(configured):
        for name in GCC_NAMES:
            gcc = os.path.join(d, name)
            if os.path.isfile(gcc):
                suffix = ".exe" if gcc.endswith(".exe") else ""
                return {"gcc": gcc, "bin": d,
                        "objcopy": os.path.join(d, "arm-none-eabi-objcopy" + suffix),
                        "size": os.path.join(d, "arm-none-eabi-size" + suffix)}
    gcc = shutil.which("arm-none-eabi-gcc")
    if gcc:
        d = os.path.dirname(gcc)
        return {"gcc": gcc, "bin": d, "objcopy": shutil.which("arm-none-eabi-objcopy") or "",
                "size": shutil.which("arm-none-eabi-size") or ""}
    return None


# ----------------------------------------------------------------- projeto
def load_config(project_dir):
    cfg = dict(DEFAULT_CONFIG)
    p = os.path.join(project_dir, CONFIG_NAME)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    return cfg


def save_config(project_dir, cfg):
    with open(os.path.join(project_dir, CONFIG_NAME), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)


TEMPLATES = {
"blank": '''#include "gba.h"

int main(void)
{
    gba_init();
    gfx_init(3);
    gfx_clear(BLACK);
    gfx_text(8, 8, "Ola, GBA!", WHITE);

    while (1) {
        vsync();
        key_poll();
    }
}
''',
"draw": '''#include "gba.h"
/* Demo da draw API: retangulo que quica, setas movem o quadrado, A troca a cor. */
int main(void)
{
    gba_init();
    gfx_init(4);                               /* modo 4: 2 paginas, sem flicker */
    u16 pal[4] = { RGB15(2, 2, 6), WHITE, RGB15(31, 12, 4), RGB15(8, 24, 31) };
    gfx_set_palette(0, pal, 4);

    int bx = 20, by = 30, vx = 2, vy = 1;      /* inteiros: sem float! */
    int px = 110, py = 70, color = 2;

    while (1) {
        key_poll();
        px += key_axis_x() * 2;
        py += key_axis_y() * 2;
        if (key_pressed(KEY_A)) color = color == 2 ? 3 : 2;

        bx += vx; by += vy;
        if (bx < 0 || bx > SCREEN_W - 24) vx = -vx;
        if (by < 16 || by > SCREEN_H - 24) vy = -vy;

        gfx_clear(0);
        gfx_text(8, 4, "LuaStudio GBA", 1);
        gfx_fill(bx, by, 24, 24, 1);
        gfx_fill(px, py, 16, 16, color);
        gfx_circle(px + 8, py + 8, 14, 1);
        gfx_text(8, 150, "frame", 1);
        gfx_int(56, 150, (int)frame_count(), 1);

        vsync();
        gfx_flip();
    }
}
''',
"sound": '''#include "gba.h"
/* Demo de som. Coloque um arquivo assets/tema.mid e descomente song_tema abaixo. */
/* #include "assets.h" */

int main(void)
{
    gba_init();
    gfx_init(3);
    gfx_clear(BLACK);
    gfx_text(8, 8, "A: beep  B: grave  L: ruido", WHITE);
    gfx_text(8, 24, "START: musica on/off", WHITE);
    /* snd_play(song_tema); */

    int paused = 0;
    while (1) {
        vsync();
        key_poll();
        if (key_pressed(KEY_A)) snd_beep(0, 81, 12, 8);      /* pulse 1, A5, 8 frames */
        if (key_pressed(KEY_B)) snd_beep(2, 45, 12, 20);     /* onda (baixo) */
        if (key_pressed(KEY_L)) snd_beep(3, 0x61, 15, 6);    /* ruido */
        if (key_pressed(KEY_START)) { paused = !paused; snd_pause(paused); }
    }
}
''',
}


def create_project(path, template="draw", **cfg_over):
    os.makedirs(os.path.join(path, "src"), exist_ok=True)
    os.makedirs(os.path.join(path, "assets"), exist_ok=True)
    cfg = dict(DEFAULT_CONFIG)
    cfg["title"] = os.path.basename(os.path.abspath(path)).upper()[:12] or "MEU JOGO"
    cfg.update(cfg_over)
    save_config(path, cfg)
    main_c = os.path.join(path, "src", "main.c")
    if not os.path.exists(main_c):
        with open(main_c, "w", encoding="utf-8") as fh:
            fh.write(TEMPLATES.get(template, TEMPLATES["blank"]))
    return cfg


# ------------------------------------------------------------------ build
class BuildResult(object):
    def __init__(self):
        self.ok = False
        self.rom = None
        self.diagnostics = []       # [(arquivo, linha, col, sev, msg)]
        self.log = []
        self.sizes = {}
        self.seconds = 0.0
        self.assets = []

    def errors(self):
        return [d for d in self.diagnostics if d[3] == "error"]

    def warnings(self):
        return [d for d in self.diagnostics if d[3] == "warning"]


_DIAG_RE = re.compile(r"^(?P<f>[^:\n]+(?::\\[^:\n]+)?):(?P<l>\d+):(?:(?P<c>\d+):)?\s*(?P<s>error|warning|fatal error):\s*(?P<m>.*)$")


def parse_gcc_output(text, base_dir=""):
    out = []
    for line in text.splitlines():
        m = _DIAG_RE.match(line.strip())
        if m:
            f = m.group("f")
            if base_dir and os.path.isabs(f):
                try:
                    f = os.path.relpath(f, base_dir)
                except ValueError:
                    pass
            sev = "error" if "error" in m.group("s") else "warning"
            out.append((f, int(m.group("l")), int(m.group("c") or 1), sev, m.group("m")))
        elif "undefined reference to" in line or "multiple definition" in line:
            out.append(("link", 0, 0, "error", line.strip()))
    return out


def parse_size(text):
    """Le a saida de `size -A` e soma por regiao: rom, iwram, ewram."""
    secs = {}
    for line in text.splitlines():
        p = line.split()
        if len(p) >= 3 and p[0].startswith(".") and p[1].isdigit():
            secs[p[0]] = int(p[1])
    rom = secs.get(".text", 0) + secs.get(".iwram", 0) + secs.get(".ewram", 0)
    iwram = secs.get(".iwram", 0) + secs.get(".bss", 0)
    ewram = secs.get(".ewram", 0) + secs.get(".sbss", 0)
    return {"rom": rom, "iwram": iwram, "ewram": ewram, "sections": secs}


def memory_warnings(sizes):
    w = []
    if sizes["rom"] > 32 * 1024 * 1024:
        w.append("ROM passa de 32MB")
    if sizes["iwram"] > 32 * 1024 - 1024:
        w.append("IWRAM %dB: restam < 1KB para a pilha (32KB total)" % sizes["iwram"])
    elif sizes["iwram"] > 28 * 1024:
        w.append("IWRAM em %dB de 32KB: pouca folga para a pilha" % sizes["iwram"])
    if sizes["ewram"] > 256 * 1024:
        w.append("EWRAM %dB passa de 256KB" % sizes["ewram"])
    return w


def _hash(*parts):
    h = hashlib.sha1()
    for p in parts:
        h.update(p if isinstance(p, bytes) else str(p).encode("utf-8"))
    return h.hexdigest()


def cflags(cfg):
    f = ["-mcpu=arm7tdmi", "-mtune=arm7tdmi", "-mthumb-interwork", cfg["opt"], "-std=gnu11",
         "-ffreestanding", "-fno-exceptions", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
         "-fomit-frame-pointer", "-ffunction-sections", "-fdata-sections",
         "-fno-tree-loop-distribute-patterns", "-Wall", "-Wextra", "-Wno-unused-parameter",
         "-Werror=implicit-function-declaration", "-Wdouble-promotion"]
    f.append("-mthumb" if cfg.get("thumb", True) else "-marm")
    if cfg.get("lto"):
        f.append("-flto")
    if cfg.get("extra_cflags"):
        f += cfg["extra_cflags"].split()
    return f


def build(project_dir, log=None, tools=None, runner=None):
    """Compila o projeto. runner(cmd)->(rc, out) e injetavel para testes."""
    t0 = time.time()
    res = BuildResult()

    def say(msg):
        res.log.append(msg)
        if log:
            log(msg)

    def run(cmd):
        if runner:
            return runner(cmd)
        p = subprocess.run(cmd, capture_output=True, text=True)
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    cfg = load_config(project_dir)
    src_dir = os.path.join(project_dir, "src")
    source_jobs = []
    if os.path.isdir(src_dir):
        for base, dirs, files in os.walk(src_dir):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for fn in sorted(files):
                if fn.endswith(".c"):
                    full = os.path.join(base, fn)
                    rel = os.path.relpath(full, src_dir).replace(os.sep, "/")
                    source_jobs.append((full, rel))
    if not source_jobs:
        raise BuildError("nenhum .c em src/ ou subpastas")

    say("[1/5] checando limites do GBA...")
    issues = limits.check_project(src_dir, allow_float=cfg["allow_float"], warn_div=cfg["warn_division"])
    for i in issues:
        res.diagnostics.append((i.file, i.line, i.col, i.severity, "[%s] %s" % (i.code, i.message)))
    # A analise estatica e consultiva: nao bloqueia a compilacao.
    # Erros reais de sintaxe, headers ou linkagem serao reportados pelo GCC.
    for i in issues:
        say(limits.format_issue(i))

    tools = tools or find_toolchain(cfg.get("toolchain_dir", ""))
    if not tools:
        raise BuildError("arm-none-eabi-gcc nao encontrado. Instale o devkitARM ou o GNU Arm Embedded "
                         "Toolchain e aponte 'toolchain_dir' nas configuracoes.")

    bdir = os.path.join(project_dir, "build")
    os.makedirs(bdir, exist_ok=True)
    say("[2/5] assets e tabelas...")
    for fn in ("gba.h", "gba_rt.c", "crt0.s", "link.ld"):
        shutil.copyfile(os.path.join(RUNTIME_DIR, fn), os.path.join(bdir, fn))
    with open(os.path.join(bdir, "gba_data.c"), "w") as fh:
        fh.write(datagen.generate_data_c())
    ah, ac, res.assets = assetmod.build_assets(os.path.join(project_dir, "assets"), cfg["mode"])
    with open(os.path.join(bdir, "assets.h"), "w") as fh:
        fh.write(ah)
    with open(os.path.join(bdir, "assets.c"), "w") as fh:
        fh.write(ac)
    for fn, info in res.assets:
        say("  asset %s -> %s B" % (fn, info.get("bytes")))

    flags = cflags(cfg)
    inc = ["-I", bdir, "-I", src_dir]
    source_dirs = {src_dir}
    headers = b""
    for base, dirs, files in os.walk(src_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        source_dirs.add(base)
        for fn in sorted(files):
            if fn.endswith(".h"):
                with open(os.path.join(base, fn), "rb") as fh:
                    headers += fh.read()
    for d in sorted(source_dirs):
        if d != src_dir:
            inc += ["-I", d]
    for fn in sorted(os.listdir(bdir)):
        if fn.endswith(".h"):
            with open(os.path.join(bdir, fn), "rb") as fh:
                headers += fh.read()
    cache_p = os.path.join(bdir, ".cache.json")
    try:
        cache = json.load(open(cache_p))
    except Exception:
        cache = {}

    jobs = []
    for full, rel in source_jobs:
        safe_obj = re.sub(r"[^A-Za-z0-9_.-]", "_", rel.replace("/", "__"))
        jobs.append((full, "u_" + safe_obj))
    jobs += [(os.path.join(bdir, f), f) for f in ("gba_rt.c", "gba_data.c", "assets.c")]
    objs, failed = [], False
    say("[3/5] compilando (%d arquivos, %s)..." % (len(jobs) + 1, cfg["opt"]))
    for path, name in jobs:
        obj = os.path.join(bdir, name[:-2] + ".o")
        objs.append(obj)
        key = _hash(" ".join(flags), open(path, "rb").read(), headers)
        if cache.get(name) == key and os.path.isfile(obj):
            continue
        cmd = [tools["gcc"], "-c", path, "-o", obj] + flags + inc
        # codigo quente e marcado IWRAM_CODE (ARM); o resto pode ser Thumb
        rc, out = run(cmd)
        diags = parse_gcc_output(out, project_dir)
        res.diagnostics += [d for d in diags if d[0] and not d[0].startswith("build")]
        if rc != 0:
            failed = True
            say(out.strip())
            cache.pop(name, None)
        else:
            cache[name] = key
            if out.strip():
                say(out.strip())
    crt_obj = os.path.join(bdir, "crt0.o")
    objs.insert(0, crt_obj)
    rc, out = run([tools["gcc"], "-c", "-x", "assembler-with-cpp", os.path.join(bdir, "crt0.s"),
                   "-o", crt_obj, "-mcpu=arm7tdmi", "-mthumb-interwork"])
    if rc != 0:
        failed = True
        say(out.strip())
        res.diagnostics += parse_gcc_output(out, project_dir)
    json.dump(cache, open(cache_p, "w"))
    if failed:
        res.seconds = time.time() - t0
        return res

    say("[4/5] ligando...")
    elf = os.path.join(bdir, "game.elf")
    link = [tools["gcc"], "-nostartfiles", "-nostdlib", "-mcpu=arm7tdmi", "-mthumb-interwork",
            "-Wl,-T," + os.path.join(bdir, "link.ld"), "-Wl,--gc-sections",
            "-Wl,-Map=" + os.path.join(bdir, "game.map")] + (["-flto", cfg["opt"]] if cfg.get("lto") else []) \
        + objs + ["-o", elf]
    rc, out = run(link + ["-lgcc"])
    if rc != 0:
        rc2, out2 = run(link)           # algumas toolchains nao trazem libgcc para armv4t
        if rc2 == 0:
            say("aviso: libgcc armv4t ausente; ligado sem -lgcc (divisao via BIOS)")
            rc, out = rc2, out2
        else:
            out = out2 or out
    if rc != 0:
        say(out.strip())
        res.diagnostics += parse_gcc_output(out, project_dir) or [("link", 0, 0, "error", out.strip()[-300:])]
        res.seconds = time.time() - t0
        return res

    say("[5/5] gerando ROM...")
    rom_path = os.path.join(project_dir, re.sub(r"[^\w\-]+", "_", cfg["title"].strip() or "game") + ".gba")
    rc, out = run([tools["objcopy"], "-O", "binary", elf, rom_path])
    if rc != 0:
        say(out.strip())
        res.diagnostics.append(("objcopy", 0, 0, "error", out.strip()))
        return res
    logo = None
    lp = os.path.join(project_dir, "logo.bin")
    if os.path.isfile(lp):
        logo = open(lp, "rb").read()
    with open(rom_path, "rb") as fh:
        rom = fh.read()
    rom = gbafix.fix_header(rom, cfg["title"], cfg["game_code"], cfg["maker"], cfg["version"], logo)
    with open(rom_path, "wb") as fh:
        fh.write(rom)
    ext = gbafix.find_external_gbafix([tools["bin"]])
    if ext and logo is None:
        ok, msg = gbafix.run_external(ext, rom_path)
        say("gbafix: %s" % ("logo gravado" if ok else msg))
        logo = True if ok else None
    if logo is None:
        say("aviso: ROM sem logo Nintendo (ok em emuladores; para console real instale gbafix "
            "ou ponha um logo.bin de 156 bytes na pasta do projeto)")
    if tools.get("size") and os.path.isfile(tools["size"]) or runner:
        rc, out = run([tools["size"], "-A", elf])
        if rc == 0:
            res.sizes = parse_size(out)
            for w in memory_warnings(res.sizes):
                res.diagnostics.append(("memoria", 0, 0, "warning", w))
                say("aviso: " + w)
            say("ROM %d B | IWRAM %d/32768 | EWRAM %d/262144" % (len(rom), res.sizes["iwram"], res.sizes["ewram"]))
    res.rom = rom_path
    res.ok = True
    res.seconds = time.time() - t0
    say("OK: %s (%.1fs)" % (os.path.basename(rom_path), res.seconds))
    return res


def run_emulator(rom_path, emulator):
    if not emulator or not os.path.isfile(emulator):
        raise BuildError("emulador nao configurado")
    subprocess.Popen([emulator, rom_path])
