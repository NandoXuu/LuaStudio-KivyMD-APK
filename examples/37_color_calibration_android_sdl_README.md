# Teste gráfico Color Calibration — Android / SDL

## Preparação

1. Copie a imagem de referência original para `assets/4k.png` na raiz do projeto LuaStudio.
2. Abra `examples/37_color_calibration_android_sdl.lua` no LuaStudio.
3. Execute usando o backend SDL no Android.
4. Toque nos sliders e nos presets para comparar brilho, contraste, saturação, realces, sombras e ganho RGB.

O exemplo usa `Graphics.ColorCalibration.Player`, respeitando os limites de ajuste do jogador e as permissões definidas pelo jogo. O preset **NEUTRO / RESET** volta os ajustes do jogador ao padrão.

## Observação sobre a imagem

O ZIP da engine recebido nesta conversa não contém o arquivo original `4k.png`. Por isso o exemplo referencia `assets/4k.png`, mas o teste só poderá mostrar a mesma imagem quando ela for copiada para esse caminho. O script exibe um aviso no status se ela estiver ausente.

## O que validar no Android

- A imagem aparece preenchendo o fundo, sem bloquear os controles.
- Os sliders respondem ao toque e os valores mudam sem erro Lua.
- A imagem realmente muda com a calibração; se somente a UI mudar ou nada mudar, verificar a ordem de composição do pass de calibração no backend SDL/OpenGL.
- Conferir orientação e escala em telas com proporções diferentes de 16:9.
- Fazer uma comparação SDR e HDR apenas em dispositivo/backend que exponha suporte HDR real; SDL por si só não garante saída HDR.
