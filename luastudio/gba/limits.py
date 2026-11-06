# -*- coding: utf-8 -*-
"""Analise estatica do C do jogo: o codigo compila com GCC normal, mas a engine impoe
limites de GBA (sem FPU, sem malloc, sem libc, pouca RAM) para o resultado ser rapido."""
import os
import re
from collections import namedtuple

Issue = namedtuple("Issue", "file line col severity code message")

BAD_INCLUDES = {
    "stdio.h": "sem libc/stdio no GBA. Use gfx_text/gfx_int/int_to_str.",
    "stdlib.h": "sem malloc/rand/qsort. Use arrays estaticos, rand_u32().",
    "math.h": "sem FPU: libm em software e ~100x mais lenta. Use fixed (24.8), fsin/fcos, isqrt32.",
    "string.h": "sem libc. memcpy/memset/memmove ja vem em gba.h; use str_len.",
    "time.h": "sem relogio. Use frame_count().", "setjmp.h": "nao suportado.",
    "signal.h": "nao suportado.", "threads.h": "nao suportado.", "pthread.h": "nao suportado.",
    "complex.h": "sem FPU.", "fenv.h": "sem FPU.", "locale.h": "nao suportado.",
}
BAD_CALLS = {
    "malloc": "sem heap. Use arrays estaticos (EWRAM_BSS para buffers grandes).",
    "calloc": "sem heap.", "realloc": "sem heap.", "free": "sem heap.",
    "printf": "use gfx_text/gfx_int.", "sprintf": "use int_to_str.", "snprintf": "use int_to_str.",
    "puts": "use gfx_text.", "fopen": "sem sistema de arquivos; embuta dados em assets/.",
    "sqrt": "use isqrt32.", "sin": "use fsin().", "cos": "use fcos().", "pow": "use shifts/tabelas.",
    "atan2": "use tabela.", "rand": "use rand_u32()/rand_range().", "srand": "use rand_seed().",
    "strlen": "use str_len().", "strcpy": "use memcpy.", "strcmp": "compare caractere a caractere.",
    "exit": "main() nunca deve retornar: use while(1).", "abort": "nao suportado.",
}
SIZES = {"u8": 1, "s8": 1, "char": 1, "u16": 2, "s16": 2, "short": 2, "u32": 4, "s32": 4,
         "int": 4, "unsigned": 4, "fixed": 4, "color_t": 2, "long": 4}
STACK_LIMIT = 1024


def strip_code(src):
    """Remove comentarios e strings preservando quebras de linha (numeros de linha intactos)."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * src.count("\n", i, j))
            i = j
        elif c in "\"'":
            q, j = c, i + 1
            while j < n and src[j] != q:
                j += 2 if src[j] == "\\" else 1
            out.append(q + " " * 0 + q)
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _is_pow2_or_const(tok):
    return bool(re.fullmatch(r"(0[xX][0-9a-fA-F]+|\d+)[uUlL]*", tok))


def check_source(name, text, allow_float=False, warn_div=True):
    issues = []
    code = strip_code(text)
    lines = text.split("\n")
    depth = 0
    for ln, line in enumerate(code.split("\n"), 1):
        raw = lines[ln - 1] if ln - 1 < len(lines) else ""
        m = re.match(r"\s*#\s*include\s*<([^>]+)>", raw)
        if m and os.path.basename(m.group(1)) in BAD_INCLUDES:
            b = os.path.basename(m.group(1))
            issues.append(Issue(name, ln, 1, "warning", "GBA001", "<%s>: %s" % (b, BAD_INCLUDES[b])))
        if line.lstrip().startswith("#"):
            continue
        for mm in re.finditer(r"\b(float|double)\b", line):
            sev = "warning"
            issues.append(Issue(name, ln, mm.start() + 1, sev, "GBA002",
                                "'%s' usa ponto flutuante em software (~100x mais lento, +2KB de ROM). "
                                "Use 'fixed' (24.8) com FIX()/fix_mul()." % mm.group(1)))
        for mm in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", line):
            fn = mm.group(1)
            if fn in BAD_CALLS and not re.search(r"\b(int|void|u32|u8|u16|char|static)\s+%s\s*\(" % fn, line):
                issues.append(Issue(name, ln, mm.start() + 1, "warning", "GBA003",
                                    "'%s' indisponivel: %s" % (fn, BAD_CALLS[fn])))
        if depth > 0 and not re.search(r"\b(static|extern)\b", line):
            for mm in re.finditer(r"\b(u8|s8|char|u16|s16|short|u32|s32|int|unsigned|fixed|color_t)\s+\**\w+\s*\[\s*(\w+)\s*\]", line):
                dim = mm.group(2)
                if dim.isdigit():
                    size = int(dim) * SIZES[mm.group(1)]
                    if size > STACK_LIMIT:
                        issues.append(Issue(name, ln, mm.start() + 1, "warning", "GBA004",
                                            "array local de %d bytes: a pilha vive na IWRAM (32KB total). "
                                            "Declare 'static' ou use EWRAM_BSS." % size))
                elif not dim.isupper():
                    issues.append(Issue(name, ln, mm.start() + 1, "warning", "GBA005",
                                        "VLA '%s[%s]': tamanho dinamico na pilha nao e permitido." % (mm.group(0).split()[-1].split("[")[0], dim)))
        if warn_div and (depth > 0 or "{" in line):
            for mm in re.finditer(r"(?<![/*])([/%])(?![/*=])\s*(\(?\s*[A-Za-z_0-9]\w*)", line):
                rhs = mm.group(2).strip("( ")
                if not _is_pow2_or_const(rhs) and not rhs.isupper():
                    issues.append(Issue(name, ln, mm.start() + 1, "warning", "GBA006",
                                        "divisao/resto por valor variavel custa ~25-50 ciclos (BIOS). "
                                        "Prefira shifts, constantes ou tabelas."))
        depth += line.count("{") - line.count("}")
    return issues


def check_project(src_dir, **kw):
    issues = []
    for base, dirs, files in os.walk(src_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fn in sorted(files):
            if fn.endswith((".c", ".h")):
                full = os.path.join(base, fn)
                rel = os.path.relpath(full, src_dir).replace(os.sep, "/")
                with open(full, encoding="utf-8", errors="replace") as fh:
                    issues += check_source(rel, fh.read(), **kw)
    return issues


def format_issue(i):
    return "%s:%d:%d: %s: [%s] %s" % (i.file, i.line, i.col, i.severity, i.code, i.message)
