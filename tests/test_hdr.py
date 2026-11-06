import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luastudio import hdr, lighting, render_config
from luastudio.runtime import Runtime


class FakeBackend(hdr.Backend):
    name = "fake"

    def __init__(self, supported=True, max_nits=1000.0, activates=True):
        self.supported = supported
        self.max_nits = max_nits
        self.activates = activates
        self.activated = 0
        self.deactivated = 0

    def probe(self):
        caps = hdr._empty_caps("fake", "" if self.supported else "tela SDR")
        caps.update(supported=self.supported, types=["HDR10"] if self.supported else [],
                    max_nits=self.max_nits if self.supported else None)
        return caps

    def activate(self, cfg, caps):
        self.activated += 1
        if self.activates:
            self.surface_ready = True
            return True, ""
        return False, "sem superficie PQ"

    def deactivate(self):
        self.deactivated += 1
        self.surface_ready = False


def make_runtime(backend=None, native=True):
    logs = []
    rt = Runtime(log=logs.append)
    rt.hdr.allow_native_output = native
    rt.hdr.set_backend(backend or FakeBackend())
    return rt, logs


class PQTest(unittest.TestCase):
    def test_valores_de_referencia(self):
        self.assertAlmostEqual(hdr.pq_encode(0.0), 0.0, places=3)
        self.assertAlmostEqual(hdr.pq_encode(10000.0), 1.0, places=6)
        self.assertAlmostEqual(hdr.pq_encode(100.0), 0.5081, places=3)
        self.assertAlmostEqual(hdr.pq_encode(203.0), 0.5807, places=3)
        self.assertAlmostEqual(hdr.pq_encode(1000.0), 0.7518, places=3)

    def test_ida_e_volta(self):
        for nits in (0.5, 10.0, 203.0, 1000.0, 4000.0):
            self.assertAlmostEqual(hdr.pq_decode(hdr.pq_encode(nits)) / nits, 1.0, places=3)

    def test_srgb_ida_e_volta(self):
        for v in (0.0, 0.02, 0.2, 0.5, 1.0):
            self.assertAlmostEqual(hdr.linear_to_srgb(hdr.srgb_to_linear(v)), v, places=5)
        self.assertGreater(hdr.srgb_to_linear(1.5), 1.0)


class GamutTest(unittest.TestCase):
    def test_branco_continua_branco(self):
        for name, mat in hdr.GAMUT_MATRICES.items():
            out = hdr.apply_matrix(mat, (1.0, 1.0, 1.0))
            for c in out:
                self.assertAlmostEqual(c, 1.0, places=3, msg=name)

    def test_vermelho_bt709_dentro_da_bt2020(self):
        r, g, b = hdr.apply_matrix(hdr.BT709_TO_BT2020, (1.0, 0.0, 0.0))
        self.assertAlmostEqual(r, 0.6274, places=3)
        self.assertGreater(g, 0.0)
        self.assertGreater(b, 0.0)


class ToneMapTest(unittest.TestCase):
    def test_branco_de_papel_preservado_e_teto(self):
        headroom = 1000.0 / 203.0
        for name in ("ACES", "Reinhard", "Hable"):
            params = hdr.tonemap_params(name, headroom)
            self.assertAlmostEqual(hdr.tonemap(1.0, params), 1.0, places=4, msg=name)
            self.assertAlmostEqual(hdr.tonemap(1e6, params), headroom, places=2, msg=name)
            prev = -1.0
            for i in range(0, 200):
                cur = hdr.tonemap(i / 10.0, params)
                self.assertGreaterEqual(cur, prev, msg=name)
                prev = cur
            self.assertGreater(hdr.tonemap(4.0, params), 1.0, msg=name)

    def test_none_so_corta_no_teto(self):
        params = hdr.tonemap_params("None", 4.0)
        self.assertEqual(hdr.tonemap(0.3, params), 0.3)
        self.assertEqual(hdr.tonemap(9.0, params), 4.0)

    def test_sem_headroom_vira_corte(self):
        params = hdr.tonemap_params("ACES", 1.0)
        self.assertEqual(params["kind"], 0.0)

    def test_sdr_nunca_passa_de_1(self):
        for name in ("ACES", "Reinhard", "Hable", "None"):
            params = hdr.tonemap_params_sdr(name)
            self.assertLessEqual(hdr.tonemap(50.0, params), 1.0)


class NormalizeTest(unittest.TestCase):
    def test_aliases_e_limites(self):
        out = hdr.normalize_hdr({"output": "hdr10", "color_space": "Rec.2020",
                                 "transfer_function": "ST2084", "tone_mapping": "aces",
                                 "paper_white_nits": 5, "peak_luminance_nits": 99999})
        self.assertEqual((out["output"], out["color_space"], out["transfer_function"],
                          out["tone_mapping"]), ("HDR10", "BT2020", "PQ", "ACES"))
        self.assertEqual(out["paper_white_nits"], hdr.PAPER_WHITE_MIN)
        self.assertEqual(out["peak_luminance_nits"], hdr.PEAK_MAX)

    def test_invalido_mantem_anterior_e_avisa(self):
        problems = []
        out = hdr.normalize_hdr({"tone_mapping": "xyz", "paper_white_nits": "abc"}, None, problems)
        self.assertEqual(out["tone_mapping"], hdr.default_hdr_config()["tone_mapping"])
        self.assertEqual(out["paper_white_nits"], 203.0)
        self.assertEqual(len(problems), 2)

    def test_pico_nunca_abaixo_do_branco_de_papel(self):
        out = hdr.normalize_hdr({"paper_white_nits": 400, "peak_luminance_nits": 200})
        self.assertEqual(out["peak_luminance_nits"], 400)

    def test_metadados_separados(self):
        out = hdr.normalize_hdr({"max_cll": 900, "max_fall": 400, "mastering_max_nits": 1000})
        self.assertEqual(out["metadata"]["max_cll"], 900)
        self.assertNotIn("max_cll", out)

    def test_render_config_guarda_hdr(self):
        cfg = render_config.normalize({"hdr": {"enabled": True, "tone_mapping": "Hable"}})
        self.assertTrue(cfg["hdr"]["enabled"])
        self.assertEqual(cfg["hdr"]["tone_mapping"], "Hable")
        again = render_config.normalize(cfg)
        self.assertEqual(again["hdr"], cfg["hdr"])


class ResolveTest(unittest.TestCase):
    def uniforms(self, **cfg):
        rt, _ = make_runtime()
        for key, value in cfg.items():
            rt.set_hdr(key, value)
        rt.set_hdr("enabled", True)
        return rt.hdr.uniforms()

    def test_branco_sdr_vira_203_nits_em_pq(self):
        u = self.uniforms()
        r, g, b = hdr.resolve_pixel((1.0, 1.0, 1.0), u)
        self.assertAlmostEqual(r, hdr.pq_encode(203.0), places=2)
        self.assertAlmostEqual(g, hdr.pq_encode(203.0), places=2)

    def test_preto_fica_preto(self):
        u = self.uniforms()
        self.assertLess(max(hdr.resolve_pixel((0.0, 0.0, 0.0), u)), 0.002)

    def test_realce_acima_de_1_chega_perto_do_pico(self):
        u = self.uniforms()
        code = hdr.resolve_pixel((4.0, 4.0, 4.0), u)[1]
        self.assertGreater(code, hdr.pq_encode(203.0))
        self.assertLessEqual(code, hdr.pq_encode(1000.0) + 1e-6)

    def test_expandir_realces_so_mexe_nos_claros(self):
        base = self.uniforms()
        boosted = self.uniforms(expand_highlights=0.5)
        dark = (0.2, 0.2, 0.2)
        self.assertEqual(hdr.resolve_pixel(dark, base), hdr.resolve_pixel(dark, boosted))
        white = (1.0, 1.0, 1.0)
        self.assertGreater(hdr.resolve_pixel(white, boosted)[0], hdr.resolve_pixel(white, base)[0])

    def test_preview_sai_em_sdr(self):
        rt, _ = make_runtime(FakeBackend(supported=False))
        rt.set_hdr("preview", True)
        rt.set_hdr("enabled", True)
        self.assertEqual(rt.hdr.mode, "preview")
        u = rt.hdr.uniforms()
        self.assertEqual(u["uHdrMode"], 0.0)
        out = hdr.resolve_pixel((0.5, 0.5, 0.5), u)
        for c in out:
            self.assertAlmostEqual(c, 0.5, places=2)

    def test_shader_declara_todos_os_uniforms(self):
        rt, _ = make_runtime()
        rt.set_hdr("enabled", True)
        for name in rt.hdr.uniforms():
            self.assertIn("uniform float %s;" % name, hdr.RESOLVE_FRAGMENT)
        types = glsl_types()
        for name in rt.hdr.uniforms():
            self.assertIn(name, types)


def glsl_types():
    from luastudio import glsl as glsl_mod
    prog = glsl_mod.SHADERS.program_2d(hdr.RESOLVE_NAME)
    return prog.types


class StateTest(unittest.TestCase):
    def test_desligado_por_padrao(self):
        rt, _ = make_runtime()
        self.assertEqual(rt.hdr.mode, "off")
        self.assertIsNone(rt.hdr.plan_entry())

    def test_liga_em_hdr10_quando_o_display_suporta(self):
        backend = FakeBackend()
        rt, logs = make_runtime(backend)
        rt.set_hdr("enabled", True)
        self.assertEqual(rt.hdr.mode, "hdr10")
        self.assertEqual(backend.activated, 1)
        self.assertIsNotNone(rt.hdr.plan_entry())
        self.assertTrue(any("HDR10 ativo" in line for line in logs))
        rt.set_hdr("enabled", False)
        self.assertEqual(rt.hdr.mode, "off")
        self.assertEqual(backend.deactivated, 1)

    def test_sem_suporte_cai_pra_sdr_sem_quebrar(self):
        rt, logs = make_runtime(FakeBackend(supported=False))
        rt.set_hdr("enabled", True)
        self.assertEqual(rt.hdr.mode, "off")
        self.assertIn("tela SDR", rt.hdr.reason)
        self.assertTrue(any("saida em SDR" in line for line in logs))

    def test_superficie_nao_confirmada_nao_emite_pq(self):
        rt, _ = make_runtime(FakeBackend(activates=False))
        rt.set_hdr("enabled", True)
        self.assertEqual(rt.hdr.mode, "off")
        self.assertIn("sem superficie PQ", rt.hdr.reason)

    def test_assume_pq_surface_forca_a_saida(self):
        backend = FakeBackend(supported=False)
        rt, _ = make_runtime(backend)
        rt.set_hdr("assume_pq_surface", True)
        rt.set_hdr("enabled", True)
        self.assertEqual(rt.hdr.mode, "hdr10")
        self.assertEqual(backend.activated, 0)

    def test_ide_nunca_emite_pq(self):
        rt, _ = make_runtime(native=False)
        rt.set_hdr("enabled", True)
        self.assertEqual(rt.hdr.mode, "off")
        self.assertIn("Player", rt.hdr.reason)

    def test_pico_limitado_pelo_display(self):
        rt, _ = make_runtime(FakeBackend(max_nits=600.0))
        rt.set_hdr("peak_luminance_nits", 1000)
        rt.set_hdr("enabled", True)
        self.assertAlmostEqual(rt.hdr.peak_nits(), 600.0)
        self.assertAlmostEqual(rt.hdr.headroom(), 600.0 / 203.0)

    def test_teto_de_cor_do_shading(self):
        rt, _ = make_runtime()
        self.assertEqual(lighting.COLOR_CEILING, 1.0)
        rt.set_hdr("enabled", True)
        self.assertAlmostEqual(lighting.COLOR_CEILING, 1000.0 / 203.0)
        rt.set_hdr("enabled", False)
        self.assertEqual(lighting.COLOR_CEILING, 1.0)

    def test_aplicar_render_reavalia(self):
        rt, _ = make_runtime()
        rt.apply_render({"hdr": {"enabled": True}})
        self.assertEqual(rt.hdr.mode, "hdr10")
        rt.apply_render({})
        self.assertEqual(rt.hdr.mode, "off")


class LuaApiTest(unittest.TestCase):
    def run_lua(self, src, backend=None):
        rt, logs = make_runtime(backend)
        ok = rt.run_source(src)
        self.assertTrue(ok, logs)
        return rt, logs

    def test_exemplo_do_pedido(self):
        src = '''
Graphics.HDR.Enabled = true
Graphics.HDR.Output = "HDR10"
Graphics.HDR.ColorSpace = "BT2020"
Graphics.HDR.TransferFunction = "PQ"
Graphics.HDR.PaperWhiteNits = 203
Graphics.HDR.PeakLuminanceNits = 1000
Graphics.HDR.ToneMapping = "ACES"
app.log(Graphics.HDR.ToneMapping, Graphics.HDR.PeakLuminanceNits, Graphics.HDR.Active)
'''
        rt, logs = self.run_lua(src)
        cfg = rt.render["hdr"]
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["tone_mapping"], "ACES")
        self.assertEqual(cfg["peak_luminance_nits"], 1000.0)
        self.assertEqual(rt.hdr.mode, "hdr10")

    def test_fallback_com_is_supported(self):
        src = '''
if Graphics.HDR.IsSupported() then
    Graphics.HDR.Enabled = true
    Graphics.HDR.Output = "HDR10"
else
    Graphics.HDR.Enabled = false
end
'''
        rt, _ = self.run_lua(src, FakeBackend(supported=False))
        self.assertFalse(rt.render["hdr"]["enabled"])
        self.assertEqual(rt.hdr.mode, "off")
        rt, _ = self.run_lua(src, FakeBackend(supported=True))
        self.assertTrue(rt.render["hdr"]["enabled"])
        self.assertTrue(rt.hdr.mode == "hdr10")

    def test_alias_minusculo_e_chamada_com_dois_pontos(self):
        src = 'graphics.HDR.Enabled = true\napp.log(tostring(graphics.HDR:IsSupported()))'
        rt, logs = self.run_lua(src)
        self.assertIn("true", logs)

    def test_valor_invalido_so_avisa(self):
        rt, logs = self.run_lua('Graphics.HDR.ToneMapping = "inexistente"\nGraphics.HDR.PaperWhiteNits = "x"')
        self.assertEqual(rt.render["hdr"]["tone_mapping"], "None")
        self.assertTrue(any("[HDR] valor invalido" in line for line in logs))

    def test_propriedade_desconhecida_avisa(self):
        _rt, logs = self.run_lua('Graphics.HDR.Brilho = 3')
        self.assertTrue(any("propriedade desconhecida" in line for line in logs))

    def test_somente_leitura(self):
        rt, logs = make_runtime()
        self.assertFalse(rt.run_source('Graphics.HDR.Active = true'))

    def test_status_e_capacidades(self):
        src = '''
local caps = Graphics.HDR.GetCapabilities()
local st = Graphics.HDR.GetStatus()
app.log(tostring(caps.Supported), tostring(caps.MaxNits), st.Mode, tostring(st.Active))
'''
        rt, logs = self.run_lua(src)
        self.assertIn("true", logs[-1])
        self.assertIn("1000", logs[-1])
        self.assertIn("SDR", logs[-1])

    def test_metadados(self):
        src = '''
Graphics.HDR.Metadata.MaxCLL = 900
Graphics.HDR.Metadata.MaxFALL = 400
Graphics.HDR.Metadata.MasteringMaxNits = 1000
'''
        rt, _ = self.run_lua(src)
        meta = rt.hdr.resolved_metadata()
        self.assertEqual((meta["max_cll"], meta["max_fall"]), (900.0, 400.0))
        self.assertEqual(meta["primaries"], "BT2020")
        self.assertFalse(rt.hdr.status_dict()["MetadataApplied"])

    def test_graphics_antigo_continua(self):
        rt, _ = self.run_lua('Graphics.setFpsLimit(60)\ngraphics.showFps(true)')
        self.assertEqual(rt.render["fps_limit"], 60)
        self.assertTrue(rt.render["show_fps"])

    def test_render_hook_recebe_hdr(self):
        rt, _ = make_runtime()
        seen = []
        rt.render_hook = seen.append
        rt.set_hdr("exposure", 2.0)
        rt.set_hdr("exposure", 2.0)
        self.assertEqual(seen, ["hdr"])


class EmissiveTest(unittest.TestCase):
    def test_emissive_soma_albedo(self):
        from luastudio import pipeline

        class Obj(object):
            props = {"Emissive": 2.0}
        self.assertEqual(pipeline._emissive(Obj), 2.0)
        Obj.props = {"Emissive": "x"}
        self.assertEqual(pipeline._emissive(Obj), 0.0)
        Obj.props = {}
        self.assertEqual(pipeline._emissive(Obj), 0.0)


if __name__ == "__main__":
    unittest.main()
