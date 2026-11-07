# LuaStudio Docs — atualização baseada na engine atual

Esta edição expande a documentação anterior com referências para:
- HDR (`Graphics.HDR`) e calibração (`Graphics.ColorCalibration`);
- captura, modo foto e pós-processamento;
- ambiente 3D, skybox cúbica, sol e ciclo dia/noite;
- relógio do mundo e pausa;
- sistemas atuais de modelos 3D/física;
- editor GBA, pipeline C e referência de `gba.h`;
- exemplos 30–38 e scripts atualizados copiados da distribuição analisada.

## Fontes analisadas
- `luas.zip`: primeira versão da engine, usada como referência histórica.
- `LuaStudio_GBA_FIXED.zip`: distribuição atual analisada.
- `luastudio-docs.zip`: documentação anterior preservada e expandida.

## Precisão
As páginas distinguem APIs expostas ao Lua, símbolos declarados no cabeçalho C do GBA e módulos internos Python. Recursos dependentes de plataforma/backend e itens explicitamente limitados são identificados como tais. A API C completa deve sempre ser conferida contra `gba.h` da mesma versão do runtime.
