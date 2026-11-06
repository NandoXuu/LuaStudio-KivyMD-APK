import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luastudio import render_config
from luastudio.runtime import Runtime


class RenderConfigTest(unittest.TestCase):
    def test_normalize(self):
        cfg = render_config.normalize({"fps_limit": "999", "texture_filter": "Pixel",
                                       "show_fps": 1, "background": "FFAA00"})
        self.assertEqual(cfg["fps_limit"], render_config.FPS_MAX)
        self.assertEqual(cfg["texture_filter"], "nearest")
        self.assertTrue(cfg["show_fps"])
        self.assertEqual(cfg["background"], "#ffaa00")

    def test_invalido_cai_no_padrao(self):
        cfg = render_config.normalize({"fps_limit": "abc", "texture_filter": "xyz",
                                       "background": "azul"})
        self.assertEqual(cfg, render_config.default_render_config())

    def test_api_lua(self):
        logs = []
        rt = Runtime(log=logs.append)
        changes = []
        rt.render_hook = changes.append
        src = ('graphics.setFpsLimit(60)\n'
               'graphics.setTextureFilter("nearest")\n'
               'graphics.showFps(true)\n'
               'graphics.setFpsLimit(60)\n'
               'app.log(graphics.fpsLimit(), graphics.textureFilter(), graphics.isShowingFps())')
        self.assertTrue(rt.run_source(src), logs)
        self.assertEqual(changes, ["fps_limit", "texture_filter", "show_fps"])
        self.assertEqual(rt.render["fps_limit"], 60)
        self.assertEqual(rt.render["texture_filter"], "nearest")

    def test_apply_render_fundo(self):
        rt = Runtime(log=lambda s: None)
        rt.apply_render({"background": "#ff0000"})
        self.assertAlmostEqual(rt.background[0], 1.0, places=2)
        self.assertAlmostEqual(rt.background[1], 0.0, places=2)


if __name__ == "__main__":
    unittest.main()
