#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ponte HTTP local: Pydroid -> Termux -> Debian/proot-distro -> ARM GCC.

Execute no Termux, nao no Pydroid:
 python tools/gba_bridge_server.py --repo-debian /sdcard/GBA_Work/lsS16-7
O servidor escuta somente em 127.0.0.1 e aceita builds de projetos no armazenamento compartilhado.
"""
import argparse
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

LOCK = threading.Lock()
BUILD_CODE = r'''import json, os, sys, traceback
from luastudio.gba import toolchain
project = sys.argv[1]
logs = []
try:
    result = toolchain.build(project, log=logs.append)
    print("__GBA_RESULT__" + json.dumps({
        "ok": result.ok, "rom": result.rom,
        "diagnostics": result.diagnostics, "sizes": result.sizes,
        "seconds": result.seconds, "assets": result.assets, "log": logs
    }))
except Exception as exc:
    print("__GBA_RESULT__" + json.dumps({"ok": False, "error": str(exc), "log": logs}))
'''


def normalize_path(path):
    """Normaliza os aliases do armazenamento compartilhado do Android."""
    path = os.path.normpath(path.strip())
    aliases = (
        ("/storage/emulated/0/", "/sdcard/"),
        ("/storage/self/primary/", "/sdcard/"),
        ("/mnt/sdcard/", "/sdcard/"),
    )
    for prefix, replacement in aliases:
        if path.startswith(prefix):
            path = replacement + path[len(prefix):]
            break
    return path


def is_allowed_project_path(path):
    """Aceita somente projetos GBA nas pastas públicas previstas pela engine.

    A engine atual cria projetos em Documents/GBA. GBA_Work é mantida para
    compatibilidade com projetos de testes/versões anteriores.
    """
    path = os.path.realpath(path)
    allowed_roots = (
        os.path.realpath("/sdcard/Documents/GBA"),
        os.path.realpath("/sdcard/GBA_Work"),
    )
    return any(path.startswith(root + os.sep) for root in allowed_roots)


class Handler(BaseHTTPRequestHandler):
    server_version = "LuaStudioGBABridge/1.2"

    def _send(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "service": "LuaStudio GBA bridge"})
        else:
            self._send(404, {"ok": False, "error": "endpoint inexistente"})

    def do_POST(self):
        if self.path != "/build":
            return self._send(404, {"ok": False, "error": "endpoint inexistente"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size <= 0 or size > 65536:
                return self._send(400, {"ok": False, "error": "requisicao invalida"})
            body = json.loads(self.rfile.read(size).decode("utf-8"))
            project = normalize_path(str(body.get("project", "")))
            if not is_allowed_project_path(project):
                return self._send(400, {"ok": False, "error": "Projeto fora das pastas GBA permitidas. Crie/abra o projeto em Documents/GBA ou use GBA_Work para projetos antigos."})
            if not os.path.isdir(project) or not os.path.isdir(os.path.join(project, "src")):
                return self._send(400, {"ok": False, "error": "Pasta do projeto nao encontrada pelo Termux."})
            if not os.path.isfile(os.path.join(project, "gba_project.json")):
                return self._send(400, {"ok": False, "error": "gba_project.json nao encontrado. Abra um projeto GBA valido."})
            cmd = ["proot-distro", "login", self.server.debian, "--",
                   "/usr/bin/env", "PYTHONPATH=" + self.server.repo_debian,
                   "/usr/bin/python3", "-c", BUILD_CODE, project]
            with LOCK:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            output = (proc.stdout or "") + (proc.stderr or "")
            marker = "__GBA_RESULT__"
            parsed = None
            for line in reversed(output.splitlines()):
                if line.startswith(marker):
                    parsed = json.loads(line[len(marker):])
                    break
            if parsed is None:
                return self._send(500, {"ok": False, "error": "Falha ao executar build no Debian (codigo %s): %s" % (proc.returncode, output[-5000:]), "log": []})
            # Inclui mensagens adicionais do processo sem duplicar o resultado JSON.
            extra = [x for x in output.splitlines() if not x.startswith(marker)]
            if extra:
                parsed.setdefault("log", []).extend(extra)
            return self._send(200, parsed)
        except subprocess.TimeoutExpired:
            return self._send(504, {"ok": False, "error": "Build excedeu 10 minutos."})
        except Exception as exc:
            return self._send(500, {"ok": False, "error": str(exc)})

    def log_message(self, fmt, *args):
        print("[GBA Bridge] " + (fmt % args))


def main():
    ap = argparse.ArgumentParser(description="Ponte local de build GBA para Lua Studio/Pydroid")
    ap.add_argument("--repo-debian", default="/sdcard/GBA_Work/lsS16-7", help="caminho do Lua Studio visto dentro do Debian")
    ap.add_argument("--debian", default="debian", help="nome da distro proot-distro")
    ap.add_argument("--host", default="127.0.0.1", help="por seguranca, mantenha 127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    if args.host not in ("127.0.0.1", "localhost"):
        ap.error("por seguranca, o servidor so pode escutar em localhost")
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    server.timeout = 1
    server.repo_debian = args.repo_debian
    server.debian = args.debian
    print("Lua Studio GBA Bridge ativo em http://127.0.0.1:%d" % args.port)
    print("Debian: %s | Lua Studio: %s" % (args.debian, args.repo_debian))
    print("Mantenha este terminal aberto enquanto compila pelo Pydroid. Ctrl+C encerra.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPonte encerrada.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
