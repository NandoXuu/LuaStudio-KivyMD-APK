import json, os, tempfile, unittest
from luastudio.ide_tools import (TabManager, VersionStore, ProjectConfig,
    create_template, color_literal, edit_line, PluginRegistry, SceneHierarchy,
    signature_hint)
from luastudio.render_config import normalize, default_render_config
from luastudio.env3d import Environment
from luastudio.diagnostics import extended_warnings

class IDEToolsTests(unittest.TestCase):
    def test_tabs_and_line_edits(self):
        t=TabManager(); t.open('a.lua','x'); t.update('y'); self.assertTrue(t.current()['dirty'])
        t.mark_saved(); self.assertFalse(t.current()['dirty'])
        result,_=edit_line('a\nb\n',0,'duplicate'); self.assertEqual(result,'a\na\nb\n')
        result,_=edit_line('a\nb\n',0,'move-down'); self.assertEqual(result,'b\na\n')
    def test_project_templates_config_and_history(self):
        with tempfile.TemporaryDirectory() as d:
            created=create_template(d,'3d'); self.assertTrue(os.path.exists(created[0]))
            cfg=ProjectConfig(d); cfg.set('fps_limit',60); cfg.save()
            self.assertEqual(ProjectConfig(d).get('fps_limit'),60)
            store=VersionStore(d,keep=2); store.snapshot(created[0],'one'); store.snapshot(created[0],'two')
            self.assertEqual(len(store.restore_list(created[0])),2)
    def test_color_plugin_scene_signature(self):
        self.assertEqual(color_literal('#f08'),'#ff0088'); self.assertIsNone(color_literal('red'))
        p=PluginRegistry(); p.register('x',hello=lambda n:n+1); self.assertEqual(p.run_hook('hello',2),[3])
        p.set_enabled('x',False); self.assertEqual(p.run_hook('hello',2),[])
        a={'Name':'Cube'}; h=SceneHierarchy([a]); h.rename(a,'Ball'); self.assertEqual(h.search('ball'),[a]); self.assertTrue(h.delete(a))
        self.assertEqual(signature_hint('Env3D.set({'), 'Env3D.set(properties)')
    def test_render_and_environment(self):
        cfg=normalize({'render_scale':4,'max_lights':999,'shader_default':'toon','fog_enabled':False},default_render_config())
        self.assertEqual(cfg['render_scale'],1.0); self.assertEqual(cfg['max_lights'],128); self.assertEqual(cfg['shader_default'],'toon')
        e=Environment(); self.assertTrue(e.set('FogDensity',0.05)); self.assertGreater(e.fog_amount(10),0)
        e.set('DayNight',True); old=e.get('WorldTime'); e.tick(2); self.assertNotEqual(e.get('WorldTime'),old)
        self.assertEqual(len(e.sky_gradient(.5)),4)
    def test_diagnostics(self):
        w=extended_warnings('local unused = 3\nwhile true do\nend')
        self.assertTrue(any('não usada' in x[1] for x in w))

if __name__=='__main__':unittest.main()
