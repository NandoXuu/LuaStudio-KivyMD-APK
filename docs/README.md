# LuaStudio Docs — Studio Edition

Documentação estática, responsiva e utilizável offline.

## Abrir
Extraia o ZIP e abra `index.html` em um navegador moderno. A pesquisa local, navegação e troca de tema continuam disponíveis. A página do assistente de IA precisa de internet e configuração própria.

## Logo da engine
1. Abra a pasta `ico/`.
2. Coloque nela o arquivo `icon.png` (idealmente quadrado, 512×512).
3. Atualize a página. O mesmo arquivo é usado no topo, na home e como favicon.

A ausência do arquivo não impede o funcionamento da documentação: o logotipo textual de fallback permanece.

## O que mudou
- Redesign visual com identidade de ferramenta de desenvolvimento: superfícies discretas, hierarquia tipográfica, fundos com luz ambiente, cards e código com maior contraste.
- Layout responsivo para desktop, tablet e celular, com menu lateral adaptado.
- Microanimações respeitando `prefers-reduced-motion`.
- Tema claro/escuro preservado.
- Novo `api-mapa.html`, separando a API Lua, classes `create.*` e subsistemas internos.
- Referência GBA reescrita usando o `gba.h` real do pacote de engine como fonte de verdade, incluindo as declarações do cabeçalho.
- Links de navegação atualizados.

## Observação sobre fidelidade da API
As páginas preexistentes foram preservadas e receberam o novo sistema visual. O mapa da API e a referência GBA foram alinhados aos fontes do pacote enviado. Para garantir que uma assinatura Lua esteja correta, confira também o registro no runtime; módulos Python internos não são automaticamente globais Lua.
