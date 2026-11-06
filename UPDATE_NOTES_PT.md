# LuaStudio 3D — atualização de ferramentas

Esta atualização amplia a base da IDE e preserva os módulos da engine existentes.

## Implementado nesta entrega

- `luastudio/ide_tools.py`: gerenciador de abas/documentos, histórico de versões, configurações por projeto, templates 2D/3D/plataforma/top-down, edição de linhas, utilitários de cores hex, assinatura de funções, adaptador genérico de hierarquia de cena e registro de hooks de plugins.
- `luastudio/prefs.py`: mais preferências e funções para importar/exportar configurações globais em JSON.
- `luastudio/render_config.py`: normalização para escala interna, limite de luzes, distância de desenho, sombras, shader padrão, encaixe de tela, orientação, VSync e opções de debug.
- `luastudio/env3d.py`: configuração por tabela, gradiente de céu, névoa exponencial e ciclo dia/noite acionado por `tick(dt)`.
- `luastudio/diagnostics.py`: avisos conservadores adicionais para variáveis locais não usadas e propriedades suspeitas.
- `luastudio/theme.py`: paletas dark, OLED, light e high-contrast, além de API para cor de destaque.
- `luastudio/editor.py` / `autocomplete.py`: expansão de templates para classes 3D, snippets e contexto de propriedades, incluindo `Env3D.set({...})`.
- `luastudio/app.py`: snapshots rotativos dos scripts antes de salvar e durante autosave quando há alterações.

## Verificação

Os testes automatizados foram executados no ambiente de desenvolvimento. Os recursos puros de lógica/configuração foram testados; não foi possível validar visualmente a aplicação em Android nem testar todos os drivers gráficos nesta execução.

## Limites que ainda exigem integração de interface/engine

Alguns recursos têm agora a lógica/base, mas não estão todos expostos como controles visuais completos: seletor de cor inline, minimapa, busca/substituição visual, multi-abas no layout principal, inspector de propriedades com sliders, hierarquia visual da cena, gráfico visual do profiler, hot reload verdadeiro do processo Player, skybox por imagem, shader PBR completo e medição real de draw calls/memória. Opções de renderização só terão efeito nos caminhos de renderização que as consumirem.

- `examples/33_california_sunset_fps.lua`: exemplo jogável de pôr do sol californiano com céu gradiente real (SkyTop/SkyBottom), sol, silhuetas e câmera FPS controlada por toque. O renderizador agora desenha o gradiente antes da geometria 3D.

## Skybox cubica de seis faces e API Sun

- A skybox pode usar seis texturas independentes: `SkyboxRight`, `SkyboxLeft`, `SkyboxTop`, `SkyboxBottom`, `SkyboxFront` e `SkyboxBack`.
- `SkyboxEnabled` ativa o modo cubico e `SkyboxSize` configura o raio do cubo centrado na camera. Faces sem textura deixam o gradiente de fallback visivel.
- `Env3D.setSkybox({ Right=..., Left=..., Top=..., Bottom=..., Front=..., Back=..., Size=... })` configura as faces em Lua.
- API `Sun`: `setTexture`, `setSize`, `enable`, `setOrbit`, `setColor`, `setDirection`, `setTime`, `getTime` e `getEnabled`.
- Exemplo completo: `examples/34_skybox_6_faces_dia_noite.lua` e texturas demonstrativas em `assets/skybox6/`.
- A projeção das faces usa a orientação e o FOV da câmera ativa. O ciclo dia/noite continua controlado por `DayNight`, `DayLength` e `WorldTime`.

## HDR10: API `Graphics.HDR`

Propriedades (leitura e escrita): `Enabled`, `Output` ("HDR10"/"SDR"), `ColorSpace` ("BT2020"/"P3"/"BT709"), `TransferFunction` ("PQ"/"Linear"), `PaperWhiteNits` (80..1000, padrão 203), `PeakLuminanceNits` (100..10000, padrão 1000), `ToneMapping` ("ACES"/"Reinhard"/"Hable"/"None", padrão "None"), `Exposure`, `ExpandHighlights` (0..1, expande os claros do conteúdo SDR em direção ao pico), `Preview` e `AssumePQSurface`.
Somente leitura: `Active`, `Mode` ("HDR10"/"Preview"/"SDR") e `Reason` (por que não está em HDR10).
Funções: `IsSupported()`, `IsActive()`, `GetCapabilities()`, `GetStatus()`, `Refresh()`.
Metadados HDR10 separados do render: `Graphics.HDR.Metadata.MaxCLL`, `MaxFALL`, `MasteringMinNits`, `MasteringMaxNits`.
Valor inválido não derruba o jogo: é ignorado com aviso `[HDR]` no log. Sem suporte, a engine cai para SDR e o script continua igual.

- `luastudio/render_config.py`: guarda e valida o bloco `hdr` (salvo no projeto e no manifest do .Lsp).
- `luastudio/hdr.py`: PQ (ST 2084), matrizes BT.709→BT.2020/P3, tone mapping ancorado no branco de papel (1.0 continua 1.0, o infinito cai no pico), shader de resolve, backends Android/Windows e a API Lua.
- `luastudio/runtime.py`: expõe `Graphics`/`graphics` com `.HDR`, `set_hdr` e `rt.hdr`.
- `luastudio/stage.py`: com HDR ligado a cena vai para Fbo RGBA float (cai para 8 bits se a GPU não renderiza/mistura em float), passa pelo postfx e termina no resolve.
- `luastudio/lighting.py`, `shading.py`, `pipeline.py`: o teto de cor do shading sobe para pico/branco de papel e `Emissive` (em `create.part`) soma brilho próprio acima de 1.0.
- `examples/35_hdr.lua` e `tests/test_hdr.py`.

### O que depende do aparelho

- Android: `IsSupported`/`GetCapabilities` usam `Display.getHdrCapabilities`/`isHdr` via jnius. Para emitir HDR10, a janela vai para `COLOR_MODE_HDR` e a superfície é marcada BT2020_PQ com `SurfaceControl.Transaction.setDataSpace` (Android 14+). Esse caminho não foi testado em aparelho; se falhar, `Mode` fica "SDR" e `Reason` diz o motivo.
- Windows: a consulta usa DisplayConfig (HDR ligado no sistema). O SDL2/Kivy entrega superfície sRGB de 8 bits, então a saída PQ real exige a camada nativa (swapchain DXGI R10G10B10A2 + ST 2084). Se a sua camada nativa já configura isso, use `Graphics.HDR.AssumePQSurface = true` para a engine emitir PQ.
- A saída HDR10 só existe no Player. Na IDE o `Mode` nunca passa de "Preview", porque a interface SDR está na mesma janela. `Preview = true` roda o pipeline HDR e mostra o resultado em SDR para ajustar tone mapping.
- Metadados ST 2086/MaxCLL/MaxFALL ficam guardados e prontos para a camada nativa; o Android não tem API pública para enviá-los (`MetadataApplied` fica false).
- Fbos de camadas/máscaras/shaders por objeto continuam em 8 bits: o conteúdo que passa por eles perde o que passa de 1.0.
- Em superfície de 8 bits o PQ mostra degraus nos gradientes; o ideal é superfície de 10 bits.


## Calibração de cor profissional: `Graphics.ColorCalibration` (SDR e HDR)

Passe de tela inteira que roda **depois do postfx e antes do resolve de HDR** (em SDR é o último passe). O tone mapping fica no resolve, então os realces são comprimidos uma única vez. Com tudo neutro (ou `Enabled = false`) o passe não executa e a imagem sai idêntica.

Ordem dos ajustes: Black/White Point e Contrast (em valor codificado sRGB) → RGB Gain/Offset (luz linear) → Highlights/Shadows (ganho com máscara suave de luminosidade) → Saturation → Brightness (em stops/EV, luz linear). Em SDR o resultado é cortado em 0..1; em HDR/Preview os valores acima de 1.0 seguem para o resolve. Aumentar o White Point não cria detalhe que não existe: em SDR o que passa do limite é recortado.

Propriedades (leitura e escrita): `Enabled`, `PlayerSettingsEnabled`, `BlackPoint` (0..0.9), `WhitePoint` (0.1..4), `Brightness` (-4..4 EV), `Contrast` (0.25..3), `Saturation` (0..3), `Highlights` e `Shadows` (-1..2), `RGB.Gain` (0..4 por canal), `RGB.Offset` (-0.5..0.5 por canal), `PlayerControls`.
`RGB.Gain`/`RGB.Offset` aceitam `{R=,G=,B=}` (canais ausentes mantêm o valor) e também `RGB.Gain.G = 1.2`.
Somente leitura: `Active`. Funções: `IsActive()`, `GetStatus()`, `Reset()` (volta o visual ao neutro e mantém permissões).
Valor inválido é ignorado e valor fora da faixa é ajustado, ambos com aviso `[ColorCalibration]` no log. `WhitePoint` é sempre mantido pelo menos 0.02 acima de `BlackPoint`.

### Controle do jogador
`PlayerSettingsEnabled = true` e `PlayerControls` (Brightness, Contrast, BlackPoint, WhitePoint, Highlights, Shadows, RGBGain, RGBOffset, Saturation) definem o que o jogador pode mexer. Uma tabela atribuída a `PlayerControls` substitui tudo: o que não aparece fica bloqueado. Padrão: só Brightness, Contrast e Saturation liberados. `PlayerControls.Shadows = true` altera apenas esse controle.

API do jogador (`Graphics.ColorCalibration.Player`): `Brightness`, `Contrast`, `BlackPoint`, `WhitePoint`, `Highlights`, `Shadows`, `Saturation`, `RGB.Gain`, `RGB.Offset`, `Reset()`, `CanAdjust(nome)`, `GetControls()`, `Get()`, `Set(tabela)`. Os ajustes são **compostos sobre o visual do jogo** (soma ou multiplicador, nunca substituem) e têm limites próprios: Brightness ±1.5 EV, Contrast ×0.7..1.4, Black ±0.1, White ±0.2, Highlights/Shadows ±0.5, Saturation ×0.5..1.5, RGB Gain ×0.8..1.25, RGB Offset ±0.05. Controle bloqueado é ignorado com aviso no log. O resultado final ainda respeita as faixas do desenvolvedor.

- `luastudio/colorcal.py`: configuração e validação, composição jogo+jogador, referência em Python do shader, shader GLSL, estado e API Lua.
- `luastudio/render_config.py`: guarda o bloco `color_calibration` (projeto e manifest do .Lsp). Ajustes do jogador são só de execução: não vão para o projeto.
- `luastudio/runtime.py` / `stage.py`: `rt.colorcal`, `Graphics.ColorCalibration`, `set_color_calibration` e o passe entre postfx e HDR.
- `examples/36_color_calibration.lua` e `tests/test_colorcal.py`.

### Limites desta entrega
- O shader GLSL não foi compilado em GPU neste ambiente (sem Kivy/OpenGL); a matemática foi validada pela referência em Python, que segue os mesmos passos.
- Não há menu de calibração embutido: o jogo monta a própria interface com `Player.*`, `GetControls()` e `Get()/Set()`. A persistência dos ajustes do jogador fica a cargo do jogo (ex.: `SaveData`).
- Fbos de camadas/máscaras/shaders por objeto continuam em 8 bits; a calibração age na imagem final da cena.


## Capture + PostProcessing
- KivyCapture integrado em `luastudio/kivycapture` (Pillow; AVI/MJPEG sem FFmpeg/OpenCV).
- Nova API Lua `Capture.Screenshot`, `Capture.Recording` e `Capture.PhotoMode`.
- `Graphics.PostProcessing` reutiliza o passe ColorCalibration antes do resolve HDR/SDR.
- Captura apontada ao widget Stage, evitando as barras e painéis do editor.
- Testes: 226 testes do Lua Studio aprovados; 39 testes KivyCapture aprovados (4 testes reais de Kivy/OpenGL pulados neste ambiente por Kivy não instalado).
