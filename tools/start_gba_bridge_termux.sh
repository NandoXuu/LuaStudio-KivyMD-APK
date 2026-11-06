#!/data/data/com.termux/files/usr/bin/bash
# Lua Studio GBA Bridge - Termux launcher
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_TERMUX="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT="${GBA_BRIDGE_PORT:-8765}"
DISTRO="${GBA_BRIDGE_DISTRO:-debian}"

# O caminho visto pelo Debian pode ser diferente do Termux.
# Pode ser sobrescrito com GBA_LS_DEBIAN_ROOT se o engine estiver em outro lugar.
to_debian_path() {
    case "$1" in
        /storage/emulated/0/*) printf '/sdcard/%s' "${1#/storage/emulated/0/}" ;;
        /storage/self/primary/*) printf '/sdcard/%s' "${1#/storage/self/primary/}" ;;
        /mnt/sdcard/*) printf '/sdcard/%s' "${1#/mnt/sdcard/}" ;;
        *) printf '%s' "$1" ;;
    esac
}
REPO_DEBIAN="${GBA_LS_DEBIAN_ROOT:-$(to_debian_path "$REPO_TERMUX")}"

fail() { echo; echo "ERRO: $*"; echo; exit 1; }

command -v python >/dev/null 2>&1 || fail "Python do Termux ausente. Execute: pkg install python -y"
command -v proot-distro >/dev/null 2>&1 || fail "proot-distro ausente. Execute: pkg install proot-distro -y"
[ -f "$SCRIPT_DIR/gba_bridge_server.py" ] || fail "Servidor nao encontrado em $SCRIPT_DIR"
[ -f "$REPO_TERMUX/luastudio/gba/toolchain.py" ] || fail "Lua Studio incompleto: $REPO_TERMUX"

echo "Verificando Debian e toolchain..."
if ! CHECK="$(proot-distro login "$DISTRO" -- /bin/sh -c \
    'command -v arm-none-eabi-gcc; command -v arm-none-eabi-objcopy; command -v arm-none-eabi-size' 2>&1)"; then
    echo "$CHECK"
    fail "Nao foi possivel executar comandos no Debian. Teste: proot-distro login $DISTRO"
fi
echo "$CHECK"
echo "$CHECK" | grep -q 'arm-none-eabi-gcc' || fail "arm-none-eabi-gcc nao encontrado no Debian. Instale gcc-arm-none-eabi."
echo "$CHECK" | grep -q 'arm-none-eabi-objcopy' || fail "arm-none-eabi-objcopy nao encontrado no Debian. Instale binutils-arm-none-eabi."

# Confere que o Debian realmente enxerga a pasta do engine usada como PYTHONPATH.
if ! proot-distro login "$DISTRO" -- /bin/sh -c \
    "test -f '$REPO_DEBIAN/luastudio/gba/toolchain.py'"; then
    fail "Debian nao encontra o Lua Studio em: $REPO_DEBIAN
Defina GBA_LS_DEBIAN_ROOT com o caminho correto visto pelo Debian."
fi

echo
echo "Lua Studio GBA Bridge: http://127.0.0.1:${PORT}"
echo "Engine no Termux: $REPO_TERMUX"
echo "Engine no Debian: $REPO_DEBIAN"
echo "Distro: $DISTRO"
echo "Mantenha este terminal aberto. Ctrl+C encerra."
exec python "$SCRIPT_DIR/gba_bridge_server.py" \
    --repo-debian "$REPO_DEBIAN" --debian "$DISTRO" \
    --host 127.0.0.1 --port "$PORT"
