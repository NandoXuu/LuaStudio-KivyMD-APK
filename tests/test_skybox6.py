import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from luastudio.runtime import Runtime
from luastudio.env3d import Environment

class TestSkybox6(unittest.TestCase):
    def test_environment_six_faces_and_size(self):
        env = Environment()
        for key in ('SkyboxRight','SkyboxLeft','SkyboxTop','SkyboxBottom','SkyboxFront','SkyboxBack'):
            self.assertTrue(env.set(key, 'assets/skybox6/%s.png' % key[7:].lower()))
            self.assertEqual(env.get(key), 'assets/skybox6/%s.png' % key[7:].lower())
        env.set('SkyboxSize', 2)
        self.assertEqual(env.get('SkyboxSize'), 10.0)
        env.set('SkyboxEnabled', True)
        self.assertTrue(env.get('SkyboxEnabled'))

    def test_lua_skybox_and_sun_api(self):
        logs=[]
        rt=Runtime(log=logs.append)
        source='''
Env3D.setSkybox({Right="assets/skybox6/right.png", Left="assets/skybox6/left.png",
 Top="assets/skybox6/top.png", Bottom="assets/skybox6/bottom.png",
 Front="assets/skybox6/front.png", Back="assets/skybox6/back.png", Size=1200})
Sun.setTexture("assets/engine/sun.png")
Sun.setSize(128)
Sun.enable(true)
Sun.setOrbit(true)
Sun.setTime(0.4)
'''
        self.assertTrue(rt.run_source(source), logs)
        self.assertTrue(rt.env3d.get('SkyboxEnabled'))
        self.assertEqual(rt.env3d.get('SkyboxSize'), 1200.0)
        self.assertEqual(rt.env3d.get('SunTexture'), 'assets/engine/sun.png')
        self.assertEqual(rt.env3d.get('SunSize'), 128.0)
        self.assertAlmostEqual(rt.env3d.get('WorldTime'), .4)

if __name__ == '__main__': unittest.main()
