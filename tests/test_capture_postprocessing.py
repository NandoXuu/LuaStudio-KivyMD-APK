
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from luastudio.runtime import Runtime


class CapturePostProcessingAPITest(unittest.TestCase):
    def setUp(self):
        self.logs = []
        self.rt = Runtime(log=self.logs.append)

    def test_capture_api_is_registered_without_importing_kivy(self):
        self.assertIsNotNone(self.rt.interp.get_global("Capture"))
        self.assertTrue(self.rt.run_source('assert(Capture.PhotoMode.IsEnabled() == false)'))

    def test_postprocessing_set_uses_existing_colorcal_pass(self):
        src = """
Graphics.PostProcessing.Set({
    Exposure = 0.5, Contrast = 1.2, Saturation = 1.1,
    Temperature = 0.25, Tint = -0.1
})
"""
        self.assertTrue(self.rt.run_source(src), self.logs)
        cfg = self.rt.render["color_calibration"]
        self.assertTrue(cfg["enabled"])
        self.assertAlmostEqual(cfg["brightness"], 0.5)
        self.assertAlmostEqual(cfg["contrast"], 1.2)
        self.assertAlmostEqual(cfg["saturation"], 1.1)
        self.assertNotEqual(cfg["rgb_gain"], [1.0, 1.0, 1.0])

    def test_postprocessing_property_and_reset(self):
        src = """
Graphics.PostProcessing.Exposure = 1.0
Graphics.PostProcessing.Saturation = 0.5
assert(Graphics.PostProcessing.Exposure == 1.0)
Graphics.PostProcessing.Reset()
"""
        self.assertTrue(self.rt.run_source(src), self.logs)
        self.assertFalse(self.rt.render["color_calibration"]["enabled"])

    def test_photo_mode_restores_calibration_and_preexisting_pause(self):
        self.rt.set_color_calibration("enabled", True)
        self.rt.set_color_calibration("brightness", 0.3)
        self.rt.worldtime.pause()
        before = dict(self.rt.render["color_calibration"])
        src = """
Capture.PhotoMode.Enable({FreezeGame = true})
Capture.PhotoMode.SetPostProcessing({Exposure = 1.4})
Capture.PhotoMode.Disable()
"""
        self.rt.interp.execute(src, "photo_mode_test.lua")
        self.assertEqual(self.rt.render["color_calibration"], before)
        self.assertTrue(self.rt.worldtime.paused)


if __name__ == "__main__":
    unittest.main()
