# Atualização de UI: Material 3 Expressive (estilo IDE)

Só a interface do editor foi alterada (o jogo/Lua/GBA/runtime não mudou).

## O que mudou
- `luastudio/theme.py` (design system novo)
  - Paleta tonal M3 escura (semente roxa): BG / SURFACE / SURFACE_2 / ACCENT (primary container) etc.
  - Escala de formas: `SHAPE_NONE/XS/S/M/L/XL/FULL` (0/4/8/12/16/28/pílula).
  - `RoundButton`: pílula + *shape morphing* ao tocar + state layer. `pill=False` e `corners=[...]` disponíveis.
  - `IconButton`: ícone tingido, conjunto ícone+rótulo centralizado.
  - Novos: `Card`, `ConnectedGroup` (grupo de botões conectados), `NavRail` (rail com indicador pill).
  - `styled_popup`: diálogo M3 (cantos 28, scrim, título à esquerda).
  - `make_input`: campo arredondado com contorno que acende no foco.
- `luastudio/app.py`: editor reorganizado como IDE: app bar flutuante, rail à esquerda
  (Código / Palco / Scripts / Saída / Plugins / Ajustes), painel em card 28, Saída em card,
  barra inferior com status + Stop + botão Executar (pílula). Configurações usam grupos conectados.
- `luastudio/home.py`: app bar em card, FAB estendido "Criar projeto", cards de projeto com cantos 28.
- `luastudio/editor.py`: editor mescla com o card; barra de símbolos em pílula flutuante.
- `luastudio/gba/editor_app.py`, `tilemap_editor_app.py`, `filebrowser.py`: cards/barras arredondados.

Compatível com a API antiga (`bg_color`, `radius`, cores `theme.*`): telas não listadas herdam o novo visual.
