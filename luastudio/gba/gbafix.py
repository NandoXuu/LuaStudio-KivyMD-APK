# -*- coding: utf-8 -*-
"""Cabecalho da ROM GBA (titulo, codigo, checksum, logo)."""
import os
import shutil
import subprocess


def checksum(rom):
    return (-(sum(rom[0xA0:0xBD]) + 0x19)) & 0xFF


def extract_logo(rom_bytes):
    """Le os 156 bytes do logo de qualquer ROM .gba existente (o logo e o mesmo em todas)."""
    if len(rom_bytes) < 0xA0 or rom_bytes[3] != 0xEA and rom_bytes[3] not in (0xEA, 0xEB):
        raise ValueError("nao parece uma ROM GBA")
    return bytes(rom_bytes[4:160])


def find_external_gbafix(extra_dirs=()):
    for d in list(extra_dirs) + [None]:
        exe = shutil.which("gbafix", path=d) if d else shutil.which("gbafix")
        if exe:
            return exe
    return None


def fix_header(rom, title, code="AGBE", maker="01", version=0, logo=None):
    """Devolve novos bytes da ROM com o cabecalho preenchido. logo=None deixa zeros
    (emuladores aceitam; hardware real exige o logo - veja find_external_gbafix/extract_logo)."""
    rom = bytearray(rom)
    if len(rom) < 0xC0:
        raise ValueError("ROM menor que o cabecalho")
    if logo is not None:
        if len(logo) != 156:
            raise ValueError("logo precisa ter 156 bytes")
        rom[4:160] = logo
    t = "".join(ch for ch in title.upper() if 32 <= ord(ch) < 127)[:12]
    rom[0xA0:0xAC] = t.encode("ascii").ljust(12, b"\0")
    rom[0xAC:0xB0] = (code.upper()[:4].ljust(4, "X")).encode("ascii")
    rom[0xB0:0xB2] = (maker.upper()[:2].ljust(2, "0")).encode("ascii")
    rom[0xB2] = 0x96
    rom[0xB3] = 0
    rom[0xB4] = 0
    rom[0xBC] = version & 255
    rom[0xBD] = checksum(rom)
    while len(rom) % 4:
        rom.append(0xFF)
    return bytes(rom)


def run_external(gbafix_exe, rom_path):
    r = subprocess.run([gbafix_exe, rom_path], capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()
