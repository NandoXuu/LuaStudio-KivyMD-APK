# -*- coding: utf-8 -*-
import os
import sys
import traceback
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))

def get_log_path():
    # No Android, tenta usar o armazenamento externo privado do aplicativo.
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        activity = PythonActivity.mActivity
        folder = activity.getExternalFilesDir(None)
        if folder is not None:
            return os.path.join(
                str(folder.getAbsolutePath()),
                "LuaStudio_startup.log"
            )
    except Exception:
        pass

    return os.path.join(BASE, "LuaStudio_startup.log")


LOG = get_log_path()

def log(message):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(
                datetime.now().strftime("[%H:%M:%S] ")
                + str(message) + "\n"
            )
    except Exception:
        pass

def log_error():
    log(traceback.format_exc())

log("========== NOVA INICIALIZACAO ==========")
log("Python: " + sys.version)
log("Diretorio: " + BASE)
log("Log: " + LOG)

sys.path.insert(0, BASE)

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "0")

log("Importando configuracao do Kivy...")

try:
    from kivy.config import Config

    Config.set("kivy", "exit_on_escape", "0")
    Config.set("graphics", "multisamples", "0")

    if Config.has_section("input"):
        for key, value in list(Config.items("input")):
            if "mtdev" in value or "hidinput" in value:
                Config.remove_option("input", key)

    log("Configuracao Kivy OK")

except Exception:
    log("ERRO NA CONFIGURACAO DO KIVY")
    log_error()

if __name__ == "__main__":
    try:
        log("Importando luastudio.app...")
        from luastudio.app import main

        log("Importacao concluida")
        log("Iniciando LuaStudio...")
        main()

        log("LuaStudio retornou de main()")

    except BaseException:
        log("ERRO FATAL NA INICIALIZACAO")
        log_error()
        raise

    finally:
        log("Fim do processo main.py")
