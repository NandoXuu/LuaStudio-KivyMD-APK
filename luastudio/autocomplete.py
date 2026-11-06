# -*- coding: utf-8 -*-
"""Context-aware completion data for LuaStudio's Lua API.

Kept independent of Kivy so it can be tested and extended by plugins.
"""
import re

TEMPLATES = {
    'part': '{ Shape = "cube", Position = {0,0,0}, Size = {1,1,1}, Color = "#4aa3ff" }',
    'model': '{ Model = "", Position = {0,0,0}, Rotation = {0,0,0}, Scale = {1,1,1} }',
    'light': '{ Type = "point", Position = {0,3,0}, Color = "#ffffff", Intensity = 1 }',
    'camera': '{ Position = {0,2,8}, Target = {0,0,0}, FOV = 60 }',
    'label': '{ Text = "Label", Position = {0,0}, Color = "#ffffff", Size = 18 }',
    'onupdate': 'function app.onupdate(dt)\n    -- Atualize a lógica do jogo aqui\nend',
    'onstart': 'function app.onstart()\n    -- Inicialize o jogo aqui\nend',
}

PROPERTIES = {
    'part': {'Shape': ['"cube"', '"sphere"', '"plane"', '"cylinder"'], 'Position': None, 'Size': None, 'Color': ['"#4aa3ff"'], 'Rotation': None, 'Material': ['"lambert"', '"toon"', '"pbr-lite"'], 'Emissive': None},
    'model': {'Model': None, 'Position': None, 'Rotation': None, 'Scale': None, 'Color': None},
    'light': {'Type': ['"point"', '"directional"', '"spot"'], 'Position': None, 'Color': ['"#ffffff"'], 'Intensity': None, 'Range': None, 'Shadows': ['true', 'false']},
    'camera': {'Position': None, 'Target': None, 'FOV': None, 'Near': None, 'Far': None},
    'label': {'Text': None, 'Position': None, 'Color': ['"#ffffff"'], 'Size': None, 'Font': None},
    'environment': {'FogColor': ['"#ffffff"'], 'FogStart': None, 'FogEnd': None, 'FogDensity': None, 'Ambient': None, 'SunDirection': None, 'SunIntensity': None, 'SunColor': ['"#ffffff"'], 'SkyTop': ['"#142952"'], 'SkyBottom': ['"#8caed1"'], 'DayNight': ['true', 'false'], 'DayLength': None, 'WorldTime': None, 'SkyTexture': ['"assets/skybox.png"'], 'SkyboxEnabled': ['true', 'false'], 'SkyboxRight': ['"assets/skybox6/right.png"'], 'SkyboxLeft': ['"assets/skybox6/left.png"'], 'SkyboxTop': ['"assets/skybox6/top.png"'], 'SkyboxBottom': ['"assets/skybox6/bottom.png"'], 'SkyboxFront': ['"assets/skybox6/front.png"'], 'SkyboxBack': ['"assets/skybox6/back.png"'], 'SkyboxSize': None, 'SkyScale': None, 'SkyOffsetX': None, 'SkyOffsetY': None, 'SkyWidth': None, 'SkyHeight': None, 'SunTexture': ['"assets/engine/sun.png"'], 'SunSize': None, 'SunEnabled': ['true', 'false'], 'SunOrbit': ['true', 'false']},
}

API_COMPLETIONS = {
    'create': ['part', 'model', 'light', 'camera', 'label'],
    'Env3D': ['set'],
    'Graphics': ['HDR', 'ColorCalibration', 'PostProcessing', 'setFpsLimit', 'fpsLimit', 'setTextureFilter', 'textureFilter', 'showFps', 'isShowingFps'],
    'HDR': ['Enabled', 'Output', 'ColorSpace', 'TransferFunction', 'PaperWhiteNits', 'PeakLuminanceNits', 'ToneMapping', 'Exposure', 'ExpandHighlights', 'Preview', 'AssumePQSurface', 'Metadata', 'Active', 'Mode', 'Reason', 'IsSupported', 'IsActive', 'GetCapabilities', 'GetStatus', 'Refresh'],
    'PostProcessing': ['Enabled', 'Exposure', 'Brightness', 'Contrast', 'Saturation', 'Temperature', 'Tint', 'Highlights', 'Shadows', 'BlackPoint', 'WhitePoint', 'Set', 'Get', 'Reset'],
    'Capture': ['Screenshot', 'Recording', 'PhotoMode', 'RequestStorageAccess', 'LastSaved'],
    'Recording': ['Start', 'Stop', 'IsRecording'],
    'PhotoMode': ['Enable', 'Disable', 'IsEnabled', 'SetPostProcessing'],
    'ColorCalibration': ['Enabled', 'PlayerSettingsEnabled', 'BlackPoint', 'WhitePoint', 'Brightness', 'Contrast', 'Saturation', 'Highlights', 'Shadows', 'RGB', 'PlayerControls', 'Player', 'Active', 'IsActive', 'GetStatus', 'Reset'],
    'Player': ['Brightness', 'Contrast', 'BlackPoint', 'WhitePoint', 'Highlights', 'Shadows', 'Saturation', 'RGB', 'Reset', 'CanAdjust', 'GetControls', 'Get', 'Set'],
    'Sun': ['setTexture', 'setSize', 'enable', 'setOrbit', 'setColor', 'setDirection', 'setTime', 'getTime', 'getEnabled'],
    'app': ['onstart', 'onupdate', 'ondraw', 'onpause', 'onresume'],
    'input': ['is_down', 'pressed', 'released', 'axis', 'pointer'],
}


def completion_context(source, cursor=None):
    """Return a small context descriptor useful for filtering suggestions."""
    if cursor is None:
        cursor = len(source)
    before = source[:cursor]
    # Detect a property table such as create.part({ Shape = ...
    match = re.search(r'create\.(part|model|light|camera|label)\s*\([^\n]*\{[^}]*$', before)
    env_match = re.search(r'Env3D\.set\s*\([^\n]*\{[^}]*$', before)
    if match or env_match:
        cls = match.group(1) if match else 'environment'
        prop = re.search(r'([A-Za-z_]\w*)\s*=\s*[^,}]*$', before)
        if prop:
            return {'kind': 'value', 'class': cls, 'property': prop.group(1)}
        return {'kind': 'property', 'class': cls}
    dotted = re.search(r'([A-Za-z_]\w*)\.([A-Za-z_]\w*)?$', before)
    if dotted:
        return {'kind': 'member', 'object': dotted.group(1), 'prefix': dotted.group(2) or ''}
    word = re.search(r'([A-Za-z_]\w*)$', before)
    return {'kind': 'word', 'prefix': word.group(1) if word else ''}


def suggestions(source, cursor=None, local_names=None):
    ctx = completion_context(source, cursor)
    if ctx['kind'] == 'property':
        return sorted(PROPERTIES.get(ctx['class'], {}))
    if ctx['kind'] == 'value':
        vals = PROPERTIES.get(ctx['class'], {}).get(ctx['property'])
        return list(vals or [])
    if ctx['kind'] == 'member':
        vals = API_COMPLETIONS.get(ctx['object'], [])
        return [v for v in vals if v.startswith(ctx['prefix'])]
    prefix = ctx.get('prefix', '')
    names = list(TEMPLATES) + list((local_names or []))
    # Identificadores locais do arquivo entram nas sugestões gerais.
    if local_names is None:
        names += re.findall(r'\blocal\s+([A-Za-z_]\w*)', source)
        names += re.findall(r'\bfunction\s+([A-Za-z_]\w*)', source)
    return sorted(set(k for k in names if k.startswith(prefix)))


def expand_snippet(name):
    return TEMPLATES.get(name)
