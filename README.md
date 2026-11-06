

## Skybox customizavel e ciclo dia/noite

O ambiente `Env3D` aceita uma imagem de céu panoramica (`SkyTexture`) ou um gradiente (`SkyTop`/`SkyBottom`). A textura e desenhada como pano de fundo e pode ser escalada e deslocada. O sol usa por padrao `assets/engine/sun.png`, que pode ser substituido via `SunTexture`.

```lua
Env3D.set({
  SkyTexture = "assets/skybox_california.png", -- imagem panoramica/de fundo
  SkyScale = 1.0, SkyWidth = 1.0, SkyHeight = 1.0,
  SkyOffsetX = 0.0, SkyOffsetY = 0.0,
  SunTexture = "assets/engine/sun.png", SunSize = 112,
  SunEnabled = true, SunOrbit = true,
  DayNight = true, DayLength = 300, WorldTime = 0.20
})
```

`WorldTime` varia de 0 a 1 para um ciclo completo. `DayLength` e a duracao em segundos do ciclo quando `DayNight = true`. `SkyWidth`, `SkyHeight` e `SkyScale` controlam a escala do pano de fundo; `SkyOffsetX/Y` deslocam a imagem. Coloque texturas dentro da pasta do projeto e use caminhos relativos. A skybox de imagem nesta versao e um pano de fundo texturizado 2D/equiretangular, nao uma skybox cubica de seis faces com amostragem por direcao de camera. O sol e um sprite texturizado desenhado sobre o ceu; sua orbita acompanha o relogio do mundo.


## Capture + PostProcessing (atualizacao)

A engine inclui `KivyCapture` internamente (Pillow como dependencia de imagem; sem
OpenCV/FFmpeg). A captura aponta para o widget `Stage` do jogo, nao para a janela
inteira do editor.

```lua
Capture.Screenshot({ Filename = "foto.png", Format = "PNG", Quality = 100 })

Capture.Recording.Start({
    Filename = "gameplay.avi", FPS = 30, Quality = 85
})
local info = Capture.Recording.Stop()
-- info.Path, info.Frames, info.DroppedFrames

Graphics.PostProcessing.Set({
    Exposure = 0.25, Contrast = 1.08, Saturation = 1.1,
    Temperature = 0.12, Tint = 0.0,
    Highlights = 0.05, Shadows = 0.1
})

Capture.PhotoMode.Enable({ FreezeGame = true })
Capture.PhotoMode.SetPostProcessing({ Exposure = 0.8, Saturation = 1.2 })
Capture.PhotoMode.Disable()
```

`Graphics.PostProcessing` reutiliza o passe `Graphics.ColorCalibration` que já é
executado depois dos postfx e antes do resolve HDR. `Exposure` é um alias de
`Brightness` (EV). Contraste, saturação, highlights, shadows e os pontos preto/
branco usam o mesmo shader existente; temperatura/tint aplicam um balanço RGB
linear aproximado. Assim, o passe continua preservando valores acima de 1.0 para
o resolve HDR10 e limita a saída no caminho SDR.

Limitações desta primeira integração:
- A gravação é AVI/MJPEG, sem áudio, com codificação em thread e fila limitada.
- `Resolution`/`Size` redimensionam a captura do Stage; não fazem supersampling
  real da cena. Captura HighResolution real exige re-renderizar a cena em FBO maior.
- O modo foto desta etapa preserva/restaura a calibração e pode pausar o relógio do
  mundo. Câmera livre, DOF físico, pose de personagem e ocultação automática de HUD
  precisam de uma API de câmera/renderização dedicada e não são simulados aqui.
- Bloom, DOF, chromatic aberration, film grain e vignette não foram adicionados
  por esta ponte: alguns exigem passes GLSL adicionais. A API registra aviso para
  parâmetros ainda não suportados em vez de fingir que os aplicou.
- No Android, KivyCapture publica mídia na galeria quando o backend MediaStore
  está disponível; em dispositivos sem o bridge Android, usa diretório privado.
