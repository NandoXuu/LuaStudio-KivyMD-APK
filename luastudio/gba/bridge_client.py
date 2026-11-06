# -*- coding: utf-8 -*-
"""Cliente da ponte local Termux -> Debian para builds GBA no Android."""
import json
import urllib.error
import urllib.request

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765"


class BridgeError(RuntimeError):
    pass


def bridge_available(url=DEFAULT_BRIDGE_URL, timeout=2.0):
    req = urllib.request.Request(url.rstrip("/") + "/health", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            return bool(data.get("ok"))
    except Exception:
        return False


def build_via_bridge(project, log=None, url=DEFAULT_BRIDGE_URL, timeout=600):
    """Solicita build remoto e devolve objeto compativel com BuildResult."""
    from .toolchain import BuildResult

    result = BuildResult()
    payload = json.dumps({"project": project}).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + "/build", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise BridgeError("Ponte GBA respondeu HTTP %s: %s" % (exc.code, detail[:1000]))
    except Exception as exc:
        raise BridgeError("Nao foi possivel conectar a ponte Termux (%s). Inicie tools/gba_bridge_server.py no Termux." % exc)

    for line in data.get("log", []):
        result.log.append(line)
        if log:
            log(line)
    result.ok = bool(data.get("ok"))
    result.rom = data.get("rom")
    result.diagnostics = [tuple(x) for x in data.get("diagnostics", [])]
    result.sizes = data.get("sizes", {})
    result.seconds = float(data.get("seconds", 0.0))
    result.assets = data.get("assets", [])
    if data.get("error"):
        raise BridgeError(data["error"])
    return result
