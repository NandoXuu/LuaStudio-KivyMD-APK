import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luastudio import model3d as m3
from luastudio import render3d
from luastudio import imagesize
from luastudio.env3d import Environment
from luastudio.runtime import Runtime
from tools import gerar_assets3d

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "assets3d")
GLB = os.path.join(ASSETS, "robo_animado.glb")
OBJ = os.path.join(ASSETS, "caixa_textura.obj")
PNG = os.path.join(ASSETS, "xadrez.png")


def run(main, base=None):
    logs = []
    rt = Runtime(log=logs.append, base_dir=base or ASSETS)
    assert rt.run_project({"main.lua": main}, "main.lua"), rt.last_error
    rt.running = True
    return rt, logs


class LoaderTest(unittest.TestCase):
    def test_obj_materials_and_textures(self):
        model = m3.load_model(OBJ)
        self.assertEqual(len(model.submeshes), 2)
        names = {sm.name: sm for sm in model.submeshes}
        self.assertIsNotNone(names["Xadrez"].texture)
        self.assertTrue(names["Xadrez"].texture.path.endswith("xadrez.png"))
        self.assertIsNone(names["Azul"].texture)
        self.assertAlmostEqual(names["Azul"].color[2], 0.95)
        self.assertEqual(model.triangle_count(), 12)

    def test_glb_rest_pose_and_skin(self):
        model = m3.load_model(GLB)
        self.assertEqual(sorted(model.clips), ["Idle", "Walk"])
        self.assertEqual([n.name for n in model.nodes], ["Base", "Topo", "Malha"])
        self.assertTrue(model.submeshes[0].texture.key.startswith("mem:"))
        rest = m3.evaluate(model, {})[0][1]
        self.assertAlmostEqual(max(p[1] for p in rest), 2.0, places=5)

    def test_glb_walk_moves_vertices(self):
        model = m3.load_model(GLB)
        pose = model.clips["Walk"].sample(0.25, model.index_of)
        moved = m3.evaluate(model, pose)[0][1]
        rest = m3.evaluate(model, {})[0][1]
        self.assertGreater(max(abs(a[2] - b[2]) for a, b in zip(moved, rest)), 0.2)

    def test_skinning_matches_manual_matrices(self):
        model = m3.load_model(GLB)
        pose = model.clips["Walk"].sample(0.25, model.index_of)
        got = m3.evaluate(model, pose)[0][1]
        root = m3.quat_from_euler(15 * math.sin(2 * math.pi * 0.25), 0, 0)
        top = m3.quat_from_euler(0, 0, -25 * math.sin(2 * math.pi * 0.25))
        base_m = m3.mat_from_trs((0, 0, 0), root, (1, 1, 1))
        top_world = m3.mat_mul(base_m, m3.mat_from_trs((0, 1, 0), top, (1, 1, 1)))
        skin_top = m3.mat_mul(top_world, m3.mat_from_trs((0, -1, 0), (0, 0, 0, 1), (1, 1, 1)))
        sm = model.submeshes[0]
        for p, jt, wt, g in zip(sm.positions, sm.joints, sm.weights, got):
            exp = [0.0, 0.0, 0.0]
            for k in range(4):
                if wt[k] == 0.0:
                    continue
                mat = base_m if jt[k] == 0 else skin_top
                q = m3.xform_point(mat, p)
                exp = [exp[i] + wt[k] * q[i] for i in range(3)]
            for i in range(3):
                self.assertAlmostEqual(exp[i], g[i], places=5)

    def test_euler_convention(self):
        q = m3.quat_from_euler(0, 0, 90)
        x, y, z = m3.xform_point(m3.mat_from_trs((0, 0, 0), q, (1, 1, 1)), (1, 0, 0))
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(y, 1.0, places=6)

    def test_clip_from_spec_is_case_insensitive(self):
        clip = m3.clip_from_spec("Pulo", {"Duration": 1, "Loop": False, "Tracks": {
            "Topo": [{"Time": 0, "Rot": [0, 0, 0]}, {"Time": 1, "Rot": [0, 0, 30]}]}})
        self.assertFalse(clip.loop)
        self.assertEqual(clip.duration, 1.0)
        self.assertIn("r", clip.tracks["Topo"])

    def test_unknown_format_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".fbx") as handle:
            with self.assertRaises(ValueError):
                m3.load_model(handle.name)

    def test_generated_assets_are_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            gerar_assets3d.gerar(tmp)
            again = m3.load_model(os.path.join(tmp, "robo_animado.glb"))
            self.assertEqual(sorted(again.clips), ["Idle", "Walk"])


class ImageSizeTest(unittest.TestCase):
    def test_png_dimensions(self):
        info = imagesize.read_image_info(PNG)
        self.assertEqual(info, {"Format": "png", "Width": 64, "Height": 64})

    def test_unknown_file_returns_none(self):
        with tempfile.NamedTemporaryFile(suffix=".bin") as handle:
            handle.write(b"nada aqui")
            handle.flush()
            self.assertIsNone(imagesize.read_image_info(handle.name))


class EnvironmentTest(unittest.TestCase):
    def test_fog_and_sun(self):
        env = Environment()
        env.set("FogStart", 5.0)
        env.set("FogEnd", 15.0)
        self.assertEqual(env.fog_amount(2.0), 0.0)
        self.assertAlmostEqual(env.fog_amount(10.0), 0.5)
        self.assertEqual(env.fog_amount(30.0), 1.0)
        env.set("FogEnd", 0.0)
        self.assertFalse(env.fog_enabled())

    def test_unknown_key_rejected(self):
        self.assertFalse(Environment().set("Inexistente", 1))

    def test_reset_restores_defaults(self):
        env = Environment()
        env.set("Ambient", 0.9)
        env.reset()
        self.assertAlmostEqual(env.ambient, 0.35)


class RenderTest(unittest.TestCase):
    def test_project_models_faces_have_uv_and_fog(self):
        rt, _ = run('''
Env3D.set({ FogStart = 3, FogEnd = 12 })
create.camera.Main = { Position = {0, 1.5, -6}, Target = {0, 1, 0}, FOV = 60 }
create.model.Robo = { Source = "assets3d/robo_animado.glb", Position = {0, 0, 0} }
''')
        cam_obj = rt.scene.camera
        cam = render3d.Camera(cam_obj.pos(), (0, 1, 0), 60.0, cam_obj.rot3())
        faces = render3d.project_models(rt.scene.of_class("model"), cam, 800, 600, rt.env3d)
        textured = [f for f in faces if f["texture"] is not None]
        self.assertGreater(len(textured), 0)
        self.assertEqual(len(textured[0]["uv"]), 3)
        self.assertEqual(len(textured[0]["points"]), 3)
        self.assertLess(render3d.apply_fog((1, 1, 1, 1), 2.0, rt.env3d)[0], 1.0 + 1e-9)
        far = render3d.apply_fog((0, 0, 0, 1), 20.0, rt.env3d)
        self.assertAlmostEqual(far[0], rt.env3d.values["FogColor"][0])

    def test_invisible_model_is_not_projected(self):
        rt, _ = run('''
create.model.Robo = { Source = "assets3d/robo_animado.glb", Position = {0, 0, 4}, Visible = false }
''')
        cam = render3d.Camera((0, 1, -6), (0, 1, 0), 60.0)
        self.assertEqual(render3d.project_models(rt.scene.of_class("model"), cam, 800, 600, rt.env3d), [])


class LuaApiTest(unittest.TestCase):
    def test_play_loop_time_and_on_end(self):
        rt, logs = run('''
create.model.Robo = { Source = "assets3d/robo_animado.glb" }
ROBO = create.model.Robo
ROBO:Play("Walk", { Loop = true, Speed = 2 })
Animation.define("Curto", { Duration = 1, Loop = false, Tracks = { Topo = { {Time=0, Rot={0,0,0}}, {Time=1, Rot={0,0,30}} } } })
ROBO:Play("Curto", { OnEnd = function(o) FIM = (FIM or 0) + 1 end })
''')
        robo = rt.scene.find("Robo")
        for _ in range(100):
            rt.update(1 / 60)
        self.assertFalse(robo.anim.playing)
        self.assertAlmostEqual(robo.anim.time, 1.0)
        self.assertEqual(rt.interp.get_global("FIM"), 1.0)

    def test_loop_wraps_time(self):
        rt, _ = run('''
create.model.Robo = { Source = "assets3d/robo_animado.glb" }
create.model.Robo:Play("Walk", { Loop = true })
''')
        robo = rt.scene.find("Robo")
        for _ in range(120):
            rt.update(1 / 60)
        self.assertTrue(robo.anim.playing)
        self.assertLess(robo.anim.time, 1.0)

    def test_pause_and_resume(self):
        rt, _ = run('''
create.model.Robo = { Source = "assets3d/robo_animado.glb" }
create.model.Robo:Play("Walk", { Loop = true })
create.model.Robo:Pause()
''')
        robo = rt.scene.find("Robo")
        for _ in range(30):
            rt.update(1 / 60)
        self.assertEqual(robo.anim.time, 0.0)
        robo.m_Resume()
        for _ in range(30):
            rt.update(1 / 60)
        self.assertGreater(robo.anim.time, 0.0)

    def test_missing_clip_logs_and_returns_false(self):
        rt, logs = run('''
create.model.Robo = { Source = "assets3d/robo_animado.glb" }
OK = create.model.Robo:Play("NaoExiste")
''')
        self.assertIs(rt.interp.get_global("OK"), False)
        self.assertTrue(any("NaoExiste" in l for l in logs))

    def test_lsa_file_loads_clips(self):
        rt, _ = run('''
N = Animation.load("assets3d/robo_clips.lsa")
TEM = Animation.has("Acenar")
''')
        self.assertEqual(rt.interp.get_global("N"), 2.0)
        self.assertTrue(rt.interp.get_global("TEM"))

    def test_models_and_images_info(self):
        rt, _ = run('''
INFO = Models.info("assets3d/robo_animado.glb")
IMG = Images.info("assets3d/xadrez.png")
EXISTE = Images.exists("assets3d/xadrez.png")
''')
        info = rt.interp.get_global("INFO")
        self.assertEqual(info.get("Name"), "robo_animado.glb")
        self.assertEqual(info.get("Triangles"), 128.0)
        img = rt.interp.get_global("IMG")
        self.assertEqual(img.get("Width"), 64.0)
        self.assertTrue(rt.interp.get_global("EXISTE"))

    def test_env3d_set_get_and_sky(self):
        rt, _ = run('''
Env3D.set({ Ambient = 0.6, Sky = "#102030", FogEnd = 50 })
A = Env3D.get("Ambient")
''')
        self.assertAlmostEqual(rt.interp.get_global("A"), 0.6)
        self.assertAlmostEqual(rt.background[0], 16 / 255.0)
        self.assertEqual(rt.env3d.values["FogEnd"], 50.0)

    def test_scene_change_resets_environment(self):
        rt, _ = run('''
Env3D.set({ Ambient = 0.9 })
''')
        rt.clear_scene()
        self.assertAlmostEqual(rt.env3d.ambient, 0.35)

    def test_broken_model_logs_without_crashing(self):
        rt, logs = run('''
create.model.Quebrado = { Source = "assets3d/nao_existe.glb" }
''')
        self.assertIsNone(rt.scene.find("Quebrado").model)
        self.assertTrue(any("nao carregou" in l for l in logs))


if __name__ == "__main__":
    unittest.main()
