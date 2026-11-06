# Lua Studio GBA — instalação no Android (Pydroid 3 + Termux + Debian)

Este guia configura o botão **Build** do Editor GBA no Pydroid 3 para solicitar a compilação ao GCC ARM instalado dentro do Debian/PRoot. O Pydroid não executa diretamente os binários Linux do Debian: o Termux mantém uma ponte HTTP local e encaminha cada compilação usando `proot-distro login`.

## 1. Requisitos

- Android com armazenamento compartilhado autorizado para Termux e Pydroid 3.
- Pydroid 3 instalado.
- Termux instalado (preferencialmente versão atual do F-Droid ou GitHub).
- Debian instalado pelo `proot-distro`.
- Projeto Lua Studio extraído em `/sdcard/GBA_Work/lsS16-7`.

> A ponte escuta somente em `127.0.0.1:8765`; não a altere para `0.0.0.0`.

## 2. Preparar o Termux (uma vez)

Abra o Termux:

```bash
pkg update && pkg upgrade -y
pkg install python proot-distro -y
termux-setup-storage
```

Aceite a permissão de arquivos do Android. Confirme que a distro existe:

```bash
proot-distro list
```

Se `debian` não estiver instalado:

```bash
proot-distro install debian
```

## 3. Preparar o Debian (uma vez)

Entre no Debian:

```bash
proot-distro login debian
```

Dentro do Debian, instale o toolchain:

```bash
apt update
apt install -y python3 gcc-arm-none-eabi binutils-arm-none-eabi make
```

Confira as ferramentas:

```bash
command -v arm-none-eabi-gcc
command -v arm-none-eabi-objcopy
command -v arm-none-eabi-size
arm-none-eabi-gcc --version
```

Os caminhos esperados no Debian são `/usr/bin/arm-none-eabi-gcc`, `/usr/bin/arm-none-eabi-objcopy` e `/usr/bin/arm-none-eabi-size`. Saia com `exit`.

## 4. Instalar/atualizar o Lua Studio

Extraia o ZIP atualizado para que a pasta fique assim:

```text
/sdcard/GBA_Work/lsS16-7/
    luastudio/
    tools/
    GBA_TUTORIAL_INSTALL.md
    GBA_TUTORIAL_INSTALL.txt
```

Se o Android extrair para uma pasta adicional, mova o conteúdo interno `lsS16-7` para `/sdcard/GBA_Work/lsS16-7`. Não deixe `tools/` aninhada duas vezes.

## 5. Iniciar a ponte (toda vez que for compilar)

No Termux, execute:

```bash
cd /sdcard/GBA_Work/lsS16-7
bash tools/start_gba_bridge_termux.sh
```

O script verifica o GCC dentro do Debian usando `proot-distro login` (não usa o subcomando inexistente `proot-distro exec`). Se estiver tudo certo, deve exibir:

```text
Iniciando Lua Studio GBA Bridge em http://127.0.0.1:8765
Mantenha este terminal aberto. Ctrl+C encerra a ponte.
```

**Deixe esse terminal aberto.** Não feche o Termux enquanto estiver compilando pelo Pydroid.

### Testar se a ponte está ativa

Abra outra sessão do Termux (sem encerrar a primeira) e execute:

```bash
python -c "from urllib.request import urlopen; print(urlopen('http://127.0.0.1:8765/health', timeout=3).read().decode())"
```

Resposta esperada contém `"ok": true`.

## 6. Compilar pelo Pydroid 3

1. Abra o Lua Studio pelo Pydroid 3.
2. Abra o Editor GBA.
3. Abra um projeto GBA criado pela engine em `Documents/GBA/` (ou um projeto legado em `/sdcard/GBA_Work/`).
4. Confirme em Configurações que `Usar compilador Termux/Debian se GCC local nao existir` está ativado.
5. Pressione **Build**.
6. A ROM `.gba` será gravada na pasta do projeto, com o nome definido em `gba_project.json`.

O servidor deve continuar aberto no Termux. O Pydroid envia apenas o caminho do projeto; a compilação ocorre no Debian.

## 7. Diagnóstico de problemas

### `Connection refused` no Pydroid

A ponte não está ouvindo na porta 8765. Volte ao Termux e inicie o script da seção 5. Se ele imprimir erro, corrija esse erro antes de pressionar Build. Teste `/health` conforme a seção 5.

### `unknown command 'exec'`

É uma mensagem de uma versão antiga do script ou de algum comando antigo. Atualize/substitua estes arquivos a partir deste ZIP:

- `tools/start_gba_bridge_termux.sh`
- `tools/gba_bridge_server.py`

A versão atual usa `proot-distro login debian -- ...`; não execute `proot-distro exec`.

### `arm-none-eabi-gcc nao encontrado`

Entre no Debian e rode:

```bash
apt update
apt install -y gcc-arm-none-eabi binutils-arm-none-eabi
```

### `Pasta do projeto nao encontrada`

A ponte aceita projetos GBA em `/sdcard/Documents/GBA/` (pasta padrão atual) e `/sdcard/GBA_Work/` (compatibilidade). Não use caminhos privados `/data/data/...` do Pydroid.

### Porta 8765 ocupada

Encerre a ponte antiga com Ctrl+C. Opcionalmente, inicie em outra porta:

```bash
GBA_BRIDGE_PORT=8766 bash tools/start_gba_bridge_termux.sh
```

Nesse caso, altere `bridge_url` no `gba_project.json` do projeto para `http://127.0.0.1:8766`.

## 8. Segurança e limitações

- A ponte aceita projetos sob `/sdcard/Documents/GBA/` e `/sdcard/GBA_Work/`; escuta apenas em loopback.
- Mantenha Termux e Pydroid atualizados e não exponha a porta na rede.
- A ponte precisa ser iniciada manualmente após reiniciar o Android ou fechar o Termux.
- A compilação real depende do runtime e do linker script do projeto; um objeto ELF ARMv4T sozinho não garante uma ROM inicializável. Teste a ROM em um emulador GBA.
