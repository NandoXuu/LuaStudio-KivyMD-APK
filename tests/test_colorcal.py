import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luastudio import colorcal, glsl, hdr, render_config
from luastudio.runtime import Runtime

NEUTRAL = colorcal.uniforms_from(colorcal.effective_settings(colorcal.default_color_calibration_config()), True)


def make_runtime():
    logs = []
    return Runtime(log=logs.append), logs


def run_lua(src):
    rt, logs = make_runtime()
    ok = rt.run_source(src)
    assert ok, logs
    return rt, logs


class MathTest(unittest.TestCase):
    def test_neutro_e_identidade(self):
        for px in ((0.0, 0.0, 0.0), (0.2, 0.5, 0.8), (1.0, 1.0, 1.0)):
            out = colorcal.calibrate_pixel(px, NEUTRAL)
            for a, b in zip(px, out):
                self.assertAlmostEqual(a, b, places=5)

    def test_neutro_preserva_realces_hdr(self):
        u = dict(NEUTRAL, uClampOutput=0.0)
        self.assertAlmostEqual(colorcal.calibrate_pixel((3.0, 3.0, 3.0), u)[0], 3.0, places=4)

    def test_sdr_corta_em_1(self):
        u = dict(NEUTRAL, uBrightness=2.0)
        self.assertEqual(colorcal.calibrate_pixel((0.9, 0.9, 0.9), u), (1.0, 1.0, 1.0))

    def test_ponto_preto_esmaga_sombras(self):
        u = dict(NEUTRAL, uBlackPoint=0.1)
        self.assertEqual(colorcal.calibrate_pixel((0.05, 0.05, 0.05), u), (0.0, 0.0, 0.0))

    def test_ponto_branco_baixo_leva_ao_branco(self):
        u = dict(NEUTRAL, uWhitePoint=0.8)
        for c in colorcal.calibrate_pixel((0.8, 0.8, 0.8), u):
            self.assertAlmostEqual(c, 1.0, places=6)

    def test_ganho_por_canal_e_linear(self):
        u = dict(NEUTRAL, uRGBGain=[2.0, 1.0, 1.0])
        r, g, b = colorcal.calibrate_pixel((0.2, 0.2, 0.2), u)
        self.assertGreater(r, g)
        self.assertAlmostEqual(g, b, places=5)
        # dobrar a luz linear = +1 stop
        lin_r = colorcal._srgb_to_linear(r)
        self.assertAlmostEqual(lin_r, 2 * colorcal._srgb_to_linear(0.2), places=4)

    def test_offset_levanta_preto(self):
        u = dict(NEUTRAL, uRGBOffset=[0.0, 0.0, 0.02])
        self.assertGreater(colorcal.calibrate_pixel((0, 0, 0), u)[2], 0.0)

    def test_realces_so_mexem_nos_claros(self):
        u = dict(NEUTRAL, uHighlights=0.5)
        dark = (0.1, 0.1, 0.1)
        self.assertEqual(colorcal.calibrate_pixel(dark, u), colorcal.calibrate_pixel(dark, NEUTRAL))
        bright = (0.7, 0.7, 0.7)
        self.assertGreater(colorcal.calibrate_pixel(bright, u)[0], 0.7)

    def test_sombras_so_mexem_nos_escuros(self):
        u = dict(NEUTRAL, uShadows=0.5)
        bright = (0.95, 0.95, 0.95)
        self.assertEqual(colorcal.calibrate_pixel(bright, u), colorcal.calibrate_pixel(bright, NEUTRAL))
        self.assertGreater(colorcal.calibrate_pixel((0.1, 0.1, 0.1), u)[0], 0.1)

    def test_sombras_nao_criam_luz_no_preto_absoluto(self):
        u = dict(NEUTRAL, uShadows=2.0)
        self.assertEqual(colorcal.calibrate_pixel((0, 0, 0), u), (0.0, 0.0, 0.0))

    def test_saturacao_zero_e_cinza(self):
        u = dict(NEUTRAL, uSaturation=0.0)
        r, g, b = colorcal.calibrate_pixel((0.9, 0.2, 0.1), u)
        self.assertAlmostEqual(r, g, places=5)
        self.assertAlmostEqual(g, b, places=5)

    def test_contraste_mantem_cinza_medio(self):
        u = dict(NEUTRAL, uContrast=1.5)
        self.assertAlmostEqual(colorcal.calibrate_pixel((0.5, 0.5, 0.5), u)[0], 0.5, places=4)
        self.assertLess(colorcal.calibrate_pixel((0.3, 0.3, 0.3), u)[0], 0.3)

    def test_nunca_negativo_nem_nan(self):
        u = dict(NEUTRAL, uContrast=3.0, uRGBOffset=[-0.5, -0.5, -0.5], uBlackPoint=0.9,
                 uWhitePoint=0.92, uShadows=-1.0, uHighlights=-1.0)
        for px in ((0, 0, 0), (0.5, 0.5, 0.5), (4, 4, 4)):
            for c in colorcal.calibrate_pixel(px, u):
                self.assertTrue(c >= 0.0 and c == c)


class NormalizeTest(unittest.TestCase):
    def test_faixas_do_desenvolvedor(self):
        probs = []
        out = colorcal.normalize_color_calibration({"contrast": 99, "rgb_gain": {"r": 9, "G": 1, "b": 1}}, problems=probs)
        self.assertEqual(out["contrast"], 3.0)
        self.assertEqual(out["rgb_gain"][0], 4.0)
        self.assertEqual(len(probs), 2)

    def test_invalido_mantem_anterior(self):
        probs = []
        out = colorcal.normalize_color_calibration({"contrast": "abc", "saturation": True}, problems=probs)
        self.assertEqual(out["contrast"], 1.0)
        self.assertEqual(out["saturation"], 1.0)
        self.assertEqual(len(probs), 2)

    def test_branco_sempre_maior_que_preto(self):
        probs = []
        out = colorcal.normalize_color_calibration({"black_point": 0.5, "white_point": 0.3}, problems=probs)
        self.assertGreaterEqual(out["white_point"] - out["black_point"], colorcal.LEVEL_GAP - 1e-9)
        self.assertTrue(probs)

    def test_canal_parcial_mantem_os_outros(self):
        base = colorcal.normalize_color_calibration({"rgb_gain": [1.1, 1.2, 1.3]})
        out = colorcal.normalize_color_calibration({"rgb_gain": {"G": 0.5}}, base)
        self.assertEqual(out["rgb_gain"], [1.1, 0.5, 1.3])

    def test_player_controls_tabela_nova_substitui(self):
        out = colorcal.normalize_color_calibration({"player_controls": {"Brightness": True, "RGBGain": True}})
        self.assertTrue(out["player_controls"]["brightness"])
        self.assertTrue(out["player_controls"]["rgb_gain"])
        self.assertFalse(out["player_controls"]["contrast"])   # ausente = negado
        self.assertFalse(out["player_controls"]["shadows"])

    def test_render_config_guarda_calibracao(self):
        cfg = render_config.normalize({"color_calibration": {"enabled": True, "contrast": 1.2}})
        self.assertTrue(cfg["color_calibration"]["enabled"])
        self.assertEqual(cfg["color_calibration"]["contrast"], 1.2)
        self.assertFalse(render_config.default_render_config()["color_calibration"]["enabled"])


class ShaderTest(unittest.TestCase):
    def test_uniforms_declarados_no_shader(self):
        prog = glsl.SHADERS.program_2d(colorcal.CALIB_NAME)
        self.assertIsNotNone(prog)
        for name in NEUTRAL:
            self.assertIn(name, prog.types)
        self.assertEqual(prog.types["uRGBGain"][0], "vec3")
        self.assertEqual(glsl.coerce_uniform(NEUTRAL["uRGBGain"], "vec3"), [1.0, 1.0, 1.0])


class StateTest(unittest.TestCase):
    def test_desligado_ou_neutro_nao_gera_passe(self):
        rt, _ = make_runtime()
        self.assertIsNone(rt.colorcal.plan_entry())
        rt.set_color_calibration("enabled", True)
        self.assertIsNone(rt.colorcal.plan_entry())          # ligado mas neutro
        rt.set_color_calibration("contrast", 1.1)
        name, uniforms = rt.colorcal.plan_entry()
        self.assertEqual(name, colorcal.CALIB_NAME)
        self.assertEqual(uniforms["uClampOutput"], 1.0)      # SDR: ultimo passe corta

    def test_com_hdr_nao_corta_realces(self):
        rt, _ = make_runtime()
        rt.set_color_calibration("enabled", True)
        rt.set_color_calibration("contrast", 1.1)
        rt.set_hdr("preview", True)
        rt.set_hdr("enabled", True)
        self.assertEqual(rt.hdr.mode, "preview")
        self.assertEqual(rt.colorcal.plan_entry()[1]["uClampOutput"], 0.0)

    def test_jogador_composto_sobre_o_visual_do_jogo(self):
        rt, _ = make_runtime()
        rt.set_color_calibration("enabled", True)
        rt.set_color_calibration("player_settings_enabled", True)
        rt.set_color_calibration("contrast", 1.2)
        rt.set_color_calibration("player_controls", {"Contrast": True})
        self.assertTrue(rt.colorcal.set_player("Contrast", 1.25))
        self.assertAlmostEqual(rt.colorcal.effective()["contrast"], 1.5, places=6)

    def test_controle_bloqueado_nao_aplica(self):
        rt, logs = make_runtime()
        rt.set_color_calibration("enabled", True)
        rt.set_color_calibration("player_settings_enabled", True)
        rt.set_color_calibration("player_controls", {"Brightness": True})
        self.assertFalse(rt.colorcal.set_player("Shadows", 0.4))
        self.assertTrue(any("nao permite" in l for l in logs))
        self.assertEqual(rt.colorcal.effective()["shadows"], 0.0)

    def test_sem_player_settings_enabled_tudo_bloqueado(self):
        rt, _ = make_runtime()
        rt.set_color_calibration("enabled", True)
        self.assertFalse(rt.colorcal.set_player("Brightness", 0.5))

    def test_limites_do_jogador(self):
        rt, logs = make_runtime()
        rt.set_color_calibration("enabled", True)
        rt.set_color_calibration("player_settings_enabled", True)
        rt.set_color_calibration("player_controls", {"Brightness": True, "RGBGain": True})
        rt.colorcal.set_player("Brightness", 50)
        rt.colorcal.set_player("RGBGain", {"R": 5, "G": 5, "B": 5})
        self.assertEqual(rt.colorcal.player["brightness"], 1.5)
        self.assertEqual(rt.colorcal.player["rgb_gain"], [1.25, 1.25, 1.25])
        self.assertTrue(any("limite do jogador" in l for l in logs))

    def test_permissao_retirada_desliga_o_efeito(self):
        rt, _ = make_runtime()
        rt.set_color_calibration("enabled", True)
        rt.set_color_calibration("player_settings_enabled", True)
        rt.set_color_calibration("player_controls", {"Brightness": True})
        rt.colorcal.set_player("Brightness", 1.0)
        self.assertEqual(rt.colorcal.effective()["brightness"], 1.0)
        rt.set_color_calibration("player_controls", {})
        self.assertEqual(rt.colorcal.effective()["brightness"], 0.0)

    def test_total_final_respeita_faixa_do_desenvolvedor(self):
        rt, _ = make_runtime()
        rt.set_color_calibration("enabled", True)
        rt.set_color_calibration("player_settings_enabled", True)
        rt.set_color_calibration("contrast", 3.0)
        rt.set_color_calibration("player_controls", {"Contrast": True})
        rt.colorcal.set_player("Contrast", 1.4)
        self.assertEqual(rt.colorcal.effective()["contrast"], 3.0)


class LuaApiTest(unittest.TestCase):
    def test_exemplo_do_pedido(self):
        rt, logs = run_lua('''
Graphics.ColorCalibration.Enabled = true
Graphics.ColorCalibration.PlayerSettingsEnabled = true
Graphics.ColorCalibration.BlackPoint = 0.02
Graphics.ColorCalibration.WhitePoint = 0.98
Graphics.ColorCalibration.Contrast = 1.10
Graphics.ColorCalibration.Saturation = 1.05
Graphics.ColorCalibration.RGB.Gain = { R = 1.08, G = 1.00, B = 1.12 }
Graphics.ColorCalibration.RGB.Offset = { R = 0.00, G = 0.00, B = 0.00 }
Graphics.ColorCalibration.Highlights = 0.25
Graphics.ColorCalibration.Shadows = 0.10
Graphics.ColorCalibration.PlayerControls = {
    Brightness = true, Contrast = true, BlackPoint = true, WhitePoint = true,
    Highlights = true, Shadows = true, RGBGain = true, RGBOffset = true, Saturation = true
}
''')
        cfg = rt.render["color_calibration"]
        self.assertTrue(cfg["enabled"] and cfg["player_settings_enabled"])
        self.assertEqual(cfg["black_point"], 0.02)
        self.assertEqual(cfg["white_point"], 0.98)
        self.assertEqual(cfg["rgb_gain"], [1.08, 1.0, 1.12])
        self.assertTrue(all(cfg["player_controls"].values()))
        self.assertTrue(rt.colorcal.is_active())
        self.assertEqual([l for l in logs if "ColorCalibration" in l], [])

    def test_exemplo_competitivo_e_leitura(self):
        rt, _ = run_lua('''
Graphics.ColorCalibration.Enabled = true
Graphics.ColorCalibration.PlayerSettingsEnabled = true
Graphics.ColorCalibration.PlayerControls = {
    Brightness = true, Contrast = true, BlackPoint = false, WhitePoint = false,
    Highlights = false, Shadows = false, RGBGain = true, RGBOffset = false, Saturation = true }
ok1 = Graphics.ColorCalibration.Player.CanAdjust("Brightness")
ok2 = Graphics.ColorCalibration.Player.CanAdjust("Shadows")
Graphics.ColorCalibration.Player.Shadows = 0.5
Graphics.ColorCalibration.Player.Brightness = 0.5
assert(ok1 == true, "Brightness deveria ser permitido")
assert(ok2 == false, "Shadows deveria ser bloqueado")
assert(Graphics.ColorCalibration.PlayerControls.RGBGain == true)
assert(Graphics.ColorCalibration.PlayerControls.Shadows == false)
''')
        self.assertEqual(rt.colorcal.player["shadows"], 0.0)
        self.assertEqual(rt.colorcal.player["brightness"], 0.5)

    def test_valores_extremos_sao_aceitos_dentro_da_faixa_e_limitados_fora(self):
        rt, logs = run_lua('''
Graphics.ColorCalibration.RGB.Gain = { R = 1.50, G = 1.50, B = 1.50 }
Graphics.ColorCalibration.Highlights = 0.50
Graphics.ColorCalibration.Shadows = 0.50
Graphics.ColorCalibration.Contrast = 1.80
Graphics.ColorCalibration.Contrast = 9
''')
        cfg = rt.render["color_calibration"]
        self.assertEqual(cfg["rgb_gain"], [1.5, 1.5, 1.5])
        self.assertEqual(cfg["contrast"], 3.0)
        self.assertTrue(any("ColorCalibration" in l for l in logs))

    def test_canal_individual_e_atribuicao_parcial(self):
        rt, _ = run_lua('''
Graphics.ColorCalibration.RGB.Gain = { R = 1.2, G = 1.0, B = 0.9 }
Graphics.ColorCalibration.RGB.Gain.G = 1.5
Graphics.ColorCalibration.PlayerControls.Shadows = true
''')
        cfg = rt.render["color_calibration"]
        self.assertEqual(cfg["rgb_gain"], [1.2, 1.5, 0.9])
        self.assertTrue(cfg["player_controls"]["shadows"])
        self.assertTrue(cfg["player_controls"]["brightness"])   # padrao preservado

    def test_propriedade_desconhecida_so_avisa(self):
        rt, logs = run_lua("Graphics.ColorCalibration.Foo = 1")
        self.assertTrue(any("Foo" in l for l in logs))

    def test_somente_leitura(self):
        rt, logs = make_runtime()
        self.assertFalse(rt.run_source("Graphics.ColorCalibration.Active = true"))

    def test_player_get_set_roundtrip(self):
        rt, _ = run_lua('''
Graphics.ColorCalibration.Enabled = true
Graphics.ColorCalibration.PlayerSettingsEnabled = true
Graphics.ColorCalibration.Player.Set({ Brightness = 0.4, Contrast = 1.1, Shadows = 0.3 })
saved = Graphics.ColorCalibration.Player.Get()
Graphics.ColorCalibration.Player.Reset()
''')
        self.assertEqual(rt.colorcal.player, colorcal.default_player_settings())

    def test_graphics_antigo_e_hdr_continuam(self):
        rt, _ = run_lua('Graphics.setFpsLimit(30)\nGraphics.HDR.Enabled = false')
        self.assertEqual(rt.render["fps_limit"], 30)


if __name__ == "__main__":
    unittest.main()
