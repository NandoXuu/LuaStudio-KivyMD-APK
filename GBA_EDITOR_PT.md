# Editor GBA (C → ROM .gba)

Fluxo: **você escreve C → o Python aciona o `arm-none-eabi-gcc` por baixo dos panos → sai a ROM `.gba`.**

- Abrir: botão **GBA** na tela inicial, ou `python gba_editor_main.py` (app separado).
- Projetos ficam em `Documentos/GBA/<nome>/` com `src/*.c`, `assets/` e `gba_project.json`.
- Precisa do toolchain ARM (o Python não traz compilador): devkitARM, GNU Arm Embedded
  (`arm-none-eabi-gcc`) ou equivalente. Aponte a pasta `bin` em **Config → Toolchain**
  ou ponha no PATH / variável `DEVKITARM`.

## Limites impostos ao C (analisados antes de compilar)
| Código | Regra |
|---|---|
| GBA001 | `<stdio.h> <stdlib.h> <math.h> <string.h> <time.h>`… proibidos (sem libc) |
| GBA002 | `float`/`double` = erro (sem FPU, ~100× mais lento). Use `fixed` 24.8 (`FIX`, `fix_mul`, `fsin`) |
| GBA003 | `malloc/free/printf/sqrt/rand/strlen…` indisponíveis (há `rand_u32`, `isqrt32`, `str_len`…) |
| GBA004 | array local > 1 KB (pilha na IWRAM de 32 KB): use `static` ou `EWRAM_BSS` |
| GBA005 | VLA proibido |
| GBA006 | aviso: `/` e `%` por variável custam 25–50 ciclos (BIOS) |

Depois do link o build confere IWRAM (32 KB), EWRAM (256 KB) e ROM (32 MB) e avisa se a pilha ficou apertada.
`allow_float` nas configurações rebaixa GBA002 para aviso.

## Otimizações embutidas
- Código quente em **IWRAM** em ARM (`IWRAM_CODE`), resto em Thumb; `-O2/-O3/-Os`, LTO opcional, `--gc-sections`.
- Draw API: preenchimento por palavras de 32 bits, `hline` sem loop por pixel, recorte único, RMW de 16 bits no modo 4 (VRAM não aceita escrita de 8 bits), texto com caminho rápido sem recorte.
- Modo 4 com duas páginas (`gfx_flip`), sprites com shadow-OAM + cópia em bloco, DMA3 para cópias grandes, `vsync()` dorme via BIOS (IntrWait).
- Divisão pelo BIOS (sem depender da libgcc armv4t), seno em tabela, `rand` xorshift, `int_to_str` sem divisão.
- Assets: PNG → tiles 4bpp com tiles repetidos removidos, bitmap 15 bits/paleta 256, LZ77 do BIOS (`lz77_compress` / `lz77_decompress`).
- Build incremental (hash por arquivo): só recompila o que mudou.

## API (resumo de `gba.h`)
`gba_init() vsync() key_poll() key_held/pressed/released()` · `gfx_init(3|4) gfx_flip() gfx_clear gfx_pixel gfx_hline gfx_vline gfx_line gfx_rect gfx_fill gfx_circle gfx_fill_circle gfx_blit gfx_set_palette` · texto `gfx_text gfx_text_bg gfx_int gfx_hex` · tiles `bg_tiles_4bpp bg_map bg_config txt_init txt_print` · sprites `spr_init spr_set spr_hide spr_flush spr_tiles spr_palette` · som `snd_play snd_stop snd_pause snd_pcm_play snd_beep`.

## Assets (pasta `assets/`)
`spr_<nome>_<W>x<H>.png` sprite sheet · `bg_<nome>.png` tileset+mapa · `img_<nome>.png` tela cheia ·
`<nome>.wav` efeito PCM 8-bit (`sfx_<nome>`) · `<nome>.mid` música (`song_<nome>`).
Os dados saem em `build/assets.h`; `#include "assets.h"` no seu C. O botão **Assets** importa e renomeia.

## MIDI otimizado
O `.mid` vira um stream de ~3 bytes por nota, tocado no ISR de VBlank nos 4 canais PSG do GBA
(2 pulse, 1 onda, 1 ruído para bateria/canal 10). Custo de CPU ≈ 0 e ROM mínima. Os 3 canais
melódicos mais usados são distribuídos (grave → onda). Efeitos PCM usam DMA + Timer0 (CPU ≈ 0).
Sem mixer de samples multi-canal nesta versão.

## O que foi e o que NÃO foi testado
Testado aqui (PC): runtime C compilada com `-DGBA_HOST` (desenho nos modos 3/4, recorte, texto, blit, LZ77, matemática, motor de música), conversores MIDI/PNG/WAV, limites, pipeline de build com toolchain simulado, templates contra a API — `python -m unittest luastudio.gba.tests.test_gba`.
**Não testado:** compilação real ARM (`crt0.s`, `link.ld`, atributos IWRAM, `-lgcc`) — não havia `arm-none-eabi-gcc` no ambiente — e a interface Kivy (não rodei Kivy). Rode o template "draw" e me mande o log de erro se algo falhar no link.
ROM sem logo Nintendo roda em emuladores; para console real use `gbafix` (detectado automaticamente) ou um `logo.bin` de 156 bytes na pasta do projeto.

## Android: Build pelo Pydroid usando Termux + Debian

O Pydroid nao executa diretamente os binarios Linux do Debian. Para compilar pelo botao **Build** no Pydroid, use a ponte HTTP local incluida nesta versao:

1. O projeto Lua Studio deve estar no armazenamento compartilhado do Android (por exemplo, `/storage/emulated/0/Documents/GBA/MeuJogo`).
2. No Termux, instale Python se necessario: `pkg install python -y`.
3. Mantenha o Debian instalado pelo `proot-distro` e confirme nele `arm-none-eabi-gcc` e `arm-none-eabi-objcopy`.
4. No Termux, entre na pasta do Lua Studio e execute `bash tools/start_gba_bridge_termux.sh`.
   - A pasta do repositorio dentro do Debian esta configurada como `/sdcard/GBA_Work/lsS16-7`.
   - Se o Lua Studio estiver em outro local, ajuste `REPO_DEBIAN` no script para o caminho equivalente visivel dentro do Debian.
5. Mantenha o Termux aberto e a ponte ativa. Ela escuta somente em `127.0.0.1:8765`.
6. Abra o Lua Studio no Pydroid, abra um projeto GBA salvo no armazenamento compartilhado e toque em **Build**.
7. Se necessario, em **Config → GBA**, deixe `Usar compilador Termux/Debian` como `True` e o endereco como `http://127.0.0.1:8765`.

O cliente usa apenas a biblioteca padrao do Python (`urllib`). O servidor recebe somente o caminho do projeto; a compilacao e executada pelo Debian. Projetos dentro da pasta privada do Pydroid nao ficam acessiveis ao Debian: mova-os para `Documents/GBA` ou outra pasta compartilhada.

Para encerrar a ponte, volte ao Termux e pressione `Ctrl+C`. A ponte nao aceita conexoes pela rede local, apenas pelo proprio aparelho.

## Editor de projeto (atualizacao)

O editor GBA agora possui um explorador de arquivos integrado ao projeto:
- Pastas expansíveis/recolhíveis e arquivos C, headers e arquivos de texto/configuração.
- Criar arquivos `.c`/`.h` e pastas na pasta selecionada.
- Renomear, duplicar, copiar, recortar/mover, colar e excluir arquivos ou pastas.
- Abas dos fontes C/H abertos, salvamento manual e indicador de alterações não salvas.
- Ações rápidas no editor: desfazer/refazer, copiar/colar, selecionar tudo, indentar/desindentar a linha e buscar texto.
- Fontes em subpastas de `src/` entram no build; headers e diretórios de include também são descobertos recursivamente.
- O analisador de limites GBA também percorre as subpastas e mantém o caminho relativo dos diagnósticos.

As operações de arquivos são limitadas ao diretório do projeto para evitar caminhos escapando da pasta do jogo. A interface foi validada por compilação sintática do Python; este ambiente não possui Kivy instalado, então a execução visual no Android/Pydroid ainda precisa ser confirmada no aparelho.
