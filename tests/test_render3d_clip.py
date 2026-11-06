import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luastudio import render3d, shading, pipeline


class FakePart(object):
    cls = "part"

    def __init__(self, shape, pos, size, rot=(0, 0, 0)):
        self.props = {"Shape": shape}
        self._pos, self._size, self._rot = pos, size, rot

    def pos(self): return self._pos
    def size(self): return self._size
    def rot3(self): return self._rot
    def color(self): return (0.5, 0.5, 0.5, 1.0)
    def axis_scale(self): return (1.0, 1.0, 1.0)


def cam(pos=(0, 3, -6)):
    return render3d.Camera(pos, (0, 0, 0), 70.0)


class ClipTest(unittest.TestCase):
    def test_clip_near_interpolates(self):
        poly = [(0, 0, 1.0, 0.0), (1, 0, -1.0, 1.0), (1, 1, -1.0, 1.0)]
        out = render3d.clip_near(poly, 0.15)
        self.assertGreaterEqual(len(out), 3)
        self.assertTrue(all(v[2] >= 0.15 - 1e-9 for v in out))

    def test_big_floor_is_visible_legacy_and_gbuffer(self):
        for size in (8, 16, 20, 40):
            floor = FakePart("plane", (0, 0, 0), (size, 1, size))
            faces = render3d.project_scene([floor], cam((0, 2, -3)), 720, 1280)
            self.assertEqual(len(faces), 1, size)
            gb = shading.build_gbuffer([floor], cam((0, 2, -3)), 720, 1280)
            self.assertEqual(len(gb), 1, size)
            self.assertEqual(len(gb[0].points), len(gb[0].world))
            self.assertEqual(len(gb[0].points), len(gb[0].uv))

    def test_plane_visible_from_above_not_below(self):
        floor = FakePart("plane", (0, 0, 0), (8, 1, 8))
        self.assertEqual(len(render3d.project_scene([floor], cam((0, 3, -6)), 720, 1280)), 1)
        self.assertEqual(len(render3d.project_scene([floor], cam((0, -3, -6)), 720, 1280)), 0)

    def test_fully_behind_camera_dropped(self):
        box = FakePart("cube", (0, 0, -20), (1, 1, 1))
        self.assertEqual(render3d.project_scene([box], cam((0, 0, -6)), 720, 1280), [])

    def test_floor_draws_before_objects(self):
        floor = FakePart("plane", (0, 0, 0), (20, 1, 20))
        far_box = FakePart("cube", (0, 1, 15), (1, 1, 1))
        faces = render3d.project_scene([far_box, floor], cam((0, 3, -6)), 720, 1280)
        self.assertEqual(faces[0]["obj"], floor)
        faces = shading.deferred_shade(
            shading.build_gbuffer([far_box, floor], cam((0, 3, -6)), 720, 1280), [])
        self.assertEqual(faces[0]["obj"], floor)


if __name__ == "__main__":
    unittest.main()
