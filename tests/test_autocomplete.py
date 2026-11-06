import unittest
from luastudio.autocomplete import completion_context, suggestions, expand_snippet

class AutocompleteTests(unittest.TestCase):
    def test_api_member_completion(self):
        self.assertEqual(suggestions('Env3D.se'), ['set'])
        self.assertIn('part', suggestions('create.pa'))

    def test_property_context(self):
        src = 'create.part({ Sh'
        self.assertEqual(completion_context(src)['kind'], 'property')
        self.assertIn('Shape', suggestions(src))

    def test_shape_value_context(self):
        src = 'create.part({ Shape = "'
        self.assertEqual(completion_context(src)['kind'], 'value')
        self.assertIn('"sphere"', suggestions(src))

    def test_part_template(self):
        template = expand_snippet('part')
        self.assertIn('Shape = "cube"', template)
        self.assertIn('Color = "#4aa3ff"', template)

if __name__ == '__main__':
    unittest.main()


class EnvironmentAutocompleteTests(unittest.TestCase):
    def test_environment_property_context(self):
        self.assertIn('FogDensity', suggestions('Env3D.set({ Fo'))
        self.assertIn('true', suggestions('Env3D.set({ DayNight = '))
