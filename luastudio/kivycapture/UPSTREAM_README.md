# KivyCapture

Captura de tela e gravação de vídeo para Kivy. Sem OpenCV, sem FFmpeg. Única dependência: **Pillow**.

```python
from kivycapture import Capture
cap = Capture()                                  # pasta padrão da plataforma
cap = Capture(output_dir=r"D:\Jogos\capturas")   # qualquer pasta/disco
cap.screenshot(on_saved=print)                   # nome automático
cap.screenshot("foto.jpg")                       # na pasta escolhida
cap.screenshot(r"E:\outra\pasta\x.png")          # caminho completo
cap.screenshot("C:/fotos/")                      # só a pasta -> nome automático
cap.start_recording("clip.avi", fps=30)
final, frames, dropped = cap.stop_recording()
```

## O que capturar (escolha livre)
```python
cap = Capture(output_dir=...)

# tela toda (padrão)
cap.screenshot()

# área livre: x, y, largura, altura em px da janela (origem topo-esquerda)
cap.screenshot(region=(100, 50, 640, 360))
cap.screenshot(region=Region(100, 50, 640, 360, origin="bottom-left"))   # origem do Kivy
cap.screenshot(region=Region(0.5, 0, 0.5, 1, unit="rel"))                 # metade direita

# um elemento/janela/popup específico (acompanha se ele se mover)
cap.screenshot(widget=meu_popup)
cap.screenshot(widget=meu_widget, isolated=True)   # renderiza só ele, mesmo coberto

# tamanho do arquivo final
cap.screenshot(region=(0, 0, 800, 600), size=(400, 300))
cap.screenshot(scale=0.5)             # metade
cap.screenshot(size=(1280, None))     # largura fixa, altura proporcional

# vídeo: os mesmos argumentos
cap.start_recording("clip.avi", fps=30, region=(100, 50, 640, 360), size=(640, None))

# alvo padrão para as próximas capturas
cap.set_region(100, 50, 640, 360);  cap.set_widget(w);  cap.set_fullscreen()
cap.set_output(size=(1280, 720))
```
**O usuário final escolhe na tela:**
```python
cap.select_region(on_done=lambda r: print(r))   # arrasta um retângulo (ESC cancela)
cap.pick_widget(on_done=lambda w: print(w))     # toca num elemento da interface
```
O seletor some antes da captura (não aparece no arquivo). Área parcialmente fora da janela mantém o tamanho pedido (parte vazia: transparente na foto, preta no vídeo); totalmente fora dá erro claro. Se o widget mudar de tamanho durante o vídeo, o quadro é ajustado ao tamanho inicial.
`widget=` captura a área como aparece na tela (rápido); `isolated=True` renderiza só o widget (mais pesado).

## Resolução pronta
```python
cap.screenshot(resolution="HD")                       # foto
cap.start_recording("clip.avi", resolution="FULL HD") # vídeo
cap.set_output(resolution="QUAD")                     # padrão das próximas capturas
```
| Nome | Lado menor da imagem |
|---|---|
| `SD` | 480 px |
| `HD` | 720 px |
| `FULL HD` | 1080 px |
| `QUAD` | 1440 px |
| `UHD` | 2160 px, limitado ao que o dispositivo entrega |

A proporção é mantida (funciona em paisagem e retrato) e a imagem nunca é aumentada: se a área capturada já for menor que a resolução pedida, sai no tamanho original. Por isso o `UHD` depende do dispositivo: em celular ou monitor de 1080p, ele sai em 1080p. `size=` e `scale=` têm prioridade sobre `resolution=`.

## Pydroid 3 / Android: salvar em qualquer pasta
```python
cap = Capture(output_dir="/storage/emulated/0/Download/pictures")
```
- Pasta escolhida = **estrita**: grava exatamente ali ou dá erro claro (`on_error` / exceção). Nada de desvio silencioso para pasta interna. Para permitir o desvio: `strict=False`.
- O Android diferencia maiúsculas: `/storage/Emulated/0/Dowloads/...` é corrigido para `/storage/emulated/0/Download/...` (caixa, `/sdcard`, `/storage/self/primary` e erro de digitação na pasta de 1º nível).
- **Permissão obrigatória (Android 11+):** em Configurações > Apps > Pydroid 3 > Permissões > Arquivos, ative *Permitir gerenciar todos os arquivos* (ou chame `Capture.request_storage_access()`, botão "Permissão" no demo). Sem isso o Android bloqueia pastas fora da área do app, e o erro dirá isso.
- Windows: `D:/pasta`, `C:\\Users\\...`, `\\\\servidor\\pasta` funcionam igual.

## Onde salva
| Plataforma | Padrão (output_dir=None) | Com output_dir |
|---|---|---|
| Windows | `Imagens\KivyCapture` e `Vídeos\KivyCapture` | qualquer caminho (C:, D:, rede `\\srv\pasta`, `~`, `%VARS%`) |
| Android | Galeria: `Pictures/KivyCapture`, `Movies/KivyCapture` (MediaStore) | a pasta informada |
| Linux/macOS | `~/Pictures/KivyCapture`, `~/Videos/KivyCapture` | qualquer caminho |

Se a pasta não existir, é criada. Sem `output_dir`, usa os padrões acima; com `output_dir` o modo é estrito (veja acima).
`on_saved(local)` recebe o local final; `on_error(exc)` recebe falhas. Tudo também aparece no log do Kivy (`KivyCapture: imagem salva em ...`).

Extras: `cap.open_folder()`, `cap.set_output_dir(...)`, `storage.pick_folder()` (desktop), `storage.export(src, destino)`.

## Android (buildozer.spec)
```
requirements = python3,kivy,pillow,pyjnius
android.permissions = WRITE_EXTERNAL_STORAGE
```
- Android 10+ (API 29+): a galeria usa MediaStore, sem permissão extra.
- Android 9 ou anterior: a permissão é pedida em runtime automaticamente.
- Pasta livre no Android 11+ exige a permissão *todos os arquivos* (ver seção Pydroid 3).

## Se der crash no Pydroid 3
Rode `exemplo_quadrado.py` (ele grava `crash_log.txt` ao lado do script). Causas já tratadas: erro de permissão do Android ao checar pastas (agora vira mensagem em `on_error`, sem derrubar o app) e leitura de pixels maior que a tela.

## Testes
```
python tests/run_tests.py               # tudo; a integração com Kivy é pulada se o Kivy não estiver instalado
python tests/run_tests.py avi math      # só alguns grupos
xvfb-run python tests/run_tests.py      # Linux sem tela: roda também a integração real com Kivy/OpenGL
```
Os testes não dependem de OpenCV nem FFmpeg. Matemática, integridade do AVI, captura simulada e caminhos Android rodam só com Pillow. A integração real precisa de Kivy e de uma janela (ou display virtual).

## Limites
- Vídeo é MJPEG (arquivos maiores que H.264); abre em VLC/mpv/Windows/Android.
- `isolated=True` é mais pesado. A leitura do framebuffer (`opengl.py`) e a parte Android (`storage.py`) precisam de teste no seu dispositivo; muxer, imagem e salvamento em pastas foram testados aqui.
