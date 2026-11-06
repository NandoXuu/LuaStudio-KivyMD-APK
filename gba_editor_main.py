# -*- coding: utf-8 -*-
"""Ponto de entrada do EDITOR GBA (C -> ROM .gba), app separado como o editor de tilemaps.

No Pydroid 3/desktop: abra este arquivo e toque em Play. Nada de pygame aqui
(mesmo motivo do main.py principal).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("KIVY_NO_ARGS", "1")
try:
    from kivy.config import Config
    Config.set("kivy", "exit_on_escape", "0")
    Config.set("graphics", "multisamples", "0")
except Exception:
    pass

if __name__ == "__main__":
    try:
        from luastudio.gba.editor_app import main
        main()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        print("[GBA Editor] ERRO FATAL AO INICIAR:\n%s" % tb)
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "GbaEditor_erro.txt"), "w", encoding="utf-8") as fh:
                fh.write(tb)
        except Exception:
            pass
        raise
