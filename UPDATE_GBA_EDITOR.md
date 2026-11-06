# LuaStudio GBA Editor — atualização do explorador de projetos

## Mudanças
- Editor com árvore de arquivos e pastas do projeto.
- Gerenciamento de arquivos e pastas: criar, renomear, duplicar, copiar, recortar/mover, colar e excluir.
- Edição de múltiplos arquivos com abas e salvamento.
- Ferramentas rápidas para desfazer/refazer, clipboard, busca e indentação.
- Compilação recursiva de arquivos `.c` em `src/` e descoberta recursiva de headers.
- Verificação de limites GBA recursiva, incluindo fontes em subpastas.
- Diagnósticos continuam navegáveis até a linha do arquivo correspondente.

## Compatibilidade e validação
- Mantém o fluxo de build local e a ponte Termux/Debian existentes.
- `python -m py_compile` passou para os módulos alterados.
- `python -m unittest luastudio.gba.tests.test_gba`: 19 testes passaram.
- Build simulado adicional com `src/game/actors/player.c` passou, confirmando compilação de fontes em subpastas.
- Kivy não está instalado no ambiente de preparação; a interface precisa ser aberta no Pydroid/Android para validação visual e de toque.
