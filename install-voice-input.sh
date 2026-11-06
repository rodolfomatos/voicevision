#!/bin/sh
#
# install-voice-input.sh — instala TUDO o necessário para voz → texto
#
# Uso:
#   sudo ./install-voice-input.sh
#
# O que faz (tudo integrado, sem passos manuais):
#   1. Instala dependências de sistema (xclip, cmake, build-essential, git, curl)
#   2. Constrói whisper.cpp e instala o binário whisper-cli em /usr/local/bin
#   3. Baixa o modelo whisper-base.bin para /models
#   4. Instala o pacote Python voicevision (pip install -e .)
#   5. Instala o script wrapper ~/.local/bin/voicevision-listen-and-copy
#   6. Configura VOICEVISION_STT_MODEL / VOICEVISION_STT_LANGUAGE em ~/.bashrc
#
# O que NÃO faz:
#   - Não configura o hotkey global (feito na UI do Cinnamon: ver docs/VOICE_INPUT.md)
#
# Sair em erro se algum comando falhar.
set -eu

echo "============================================================"
echo "  voicevision — instalador completo de voz → texto"
echo "============================================================"
echo ""

# --- 0. Detetar utilizador alvo (quem chamou o sudo) ---
TARGET_USER="${SUDO_USER:-$(whoami)}"
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
if [ -z "$TARGET_HOME" ]; then
    echo "Erro: não foi possível detetar o home do utilizador '$TARGET_USER'" >&2
    exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Utilizador alvo: $TARGET_USER"
echo "Home: $TARGET_HOME"
echo "Projeto: $PROJECT_ROOT"
echo ""

# --- 1. Instalar dependências de sistema ---
echo "[1/6] Instalando dependências de sistema..."
if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y xclip cmake build-essential git curl python3-pip
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y xclip cmake gcc gcc-c++ make git curl python3-pip
elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm xclip cmake base-devel git curl python-pip
else
    echo "Erro: gestor de pacotes não detetado. Instale manualmente: xclip, cmake, build-essential, git, curl, python3-pip" >&2
    exit 1
fi

for cmd in xclip cmake curl git pip3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "Erro: '$cmd' não foi instalado e é obrigatório." >&2
        exit 1
    fi
done
echo "  ✓ dependências de sistema instaladas"
echo ""

# --- 2. Construir whisper.cpp e instalar whisper-cli ---
echo "[2/6] Construindo whisper.cpp (whisper-cli)..."
WHISPER_DIR="/tmp/whispercpp-build-$$"
rm -rf "$WHISPER_DIR"
git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git "$WHISPER_DIR"
cd "$WHISPER_DIR"
cmake -B build -DCMAKE_BUILD_TYPE=Release >/dev/null 2>&1
cmake --build build --target whisper-cli -j"$(nproc)" >/dev/null 2>&1
install -m 0755 -o root -g root build/bin/whisper-cli /usr/local/bin/whisper-cli
cd /
rm -rf "$WHISPER_DIR"

if ! command -v whisper-cli >/dev/null 2>&1; then
    echo "Erro: whisper-cli não foi instalado em /usr/local/bin." >&2
    exit 1
fi
echo "  ✓ whisper-cli instalado: $(command -v whisper-cli)"
echo ""

# --- 3. Baixar modelo STT para /models ---
echo "[3/6] Baixando modelo STT (whisper-base.bin) para /models..."
mkdir -p /models
chown "$TARGET_USER":"$TARGET_USER" /models

MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin"
MODEL_PATH="/models/whisper-base.bin"

if [ ! -f "$MODEL_PATH" ]; then
    curl -L -sS --fail "$MODEL_URL" -o "$MODEL_PATH"
    chown "$TARGET_USER":"$TARGET_USER" "$MODEL_PATH"
fi

if [ ! -s "$MODEL_PATH" ]; then
    echo "Erro: não foi possível baixar o modelo STT." >&2
    exit 1
fi

MODEL_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
echo "  ✓ modelo STT: $MODEL_PATH ($MODEL_SIZE)"
echo ""

# --- 4. Instalar pacote Python voicevision (com extra de áudio) ---
echo "[4/6] Instalando pacote Python voicevision (com suporte a áudio)..."
cd "$PROJECT_ROOT"
if ! python3 -m pip install --break-system-packages --ignore-installed -e . ; then
    echo "Erro: falha ao instalar o pacote Python voicevision." >&2
    echo "Tente executar manualmente: cd $PROJECT_ROOT && python3 -m pip install --break-system-packages --ignore-installed -e ." >&2
    exit 1
fi

# sounddevice é um extra opcional do voicevision; precisa dele para captura de microfone
if ! python3 -c "import sounddevice" 2>/dev/null; then
    echo "  ⚠ sounddevice não encontrado — instalando extra de áudio..."
    if ! python3 -m pip install --break-system-packages "sounddevice>=0.4.6" ; then
        echo "Erro: falha ao instalar sounddevice (captura de microfone)." >&2
        echo "Tente: python3 -m pip install --break-system-packages sounddevice>=0.4.6" >&2
        exit 1
    fi
fi

if ! command -v voicevision-listen >/dev/null 2>&1; then
    echo "Erro: voicevision-listen não está no PATH após a instalação do pacote." >&2
    exit 1
fi
echo "  ✓ voicevision-listen instalado: $(command -v voicevision-listen)"
echo ""

# --- 5. Instalar script wrapper ---
echo "[5/6] Instalando script wrapper..."
WRAPPER_SRC="$PROJECT_ROOT/scripts/voicevision-listen-and-copy.sh"
WRAPPER_DST="$TARGET_HOME/.local/bin/voicevision-listen-and-copy"

mkdir -p "$TARGET_HOME/.local/bin"
install -m 0755 -o "$TARGET_USER" -g "$TARGET_USER" "$WRAPPER_SRC" "$WRAPPER_DST"

if [ ! -x "$WRAPPER_DST" ]; then
    echo "Erro: wrapper não está executável em $WRAPPER_DST." >&2
    exit 1
fi
echo "  ✓ wrapper instalado: $WRAPPER_DST"
echo ""

# --- 6. Configurar variáveis de ambiente ---
echo "[6/6] Configurando variáveis de ambiente em ~/.bashrc..."
BASHRC="$TARGET_HOME/.bashrc"
touch "$BASHRC"
chown "$TARGET_USER":"$TARGET_USER" "$BASHRC" 2>/dev/null || true

if ! grep -q "VOICEVISION_STT_MODEL" "$BASHRC"; then
    cat >> "$BASHRC" <<'BASHRC_EOF'

# voicevision — configuração de STT (voz → texto)
export VOICEVISION_STT_MODEL="/models/whisper-base.bin"
export VOICEVISION_STT_LANGUAGE="pt"
BASHRC_EOF
    chown "$TARGET_USER":"$TARGET_USER" "$BASHRC" 2>/dev/null || true
    echo "  ✓ variáveis adicionadas a ~/.bashrc"
else
    echo "  ⚠ VOICEVISION_STT_MODEL já está em ~/.bashrc — não foi alterado"
fi
echo ""

# --- Resumo ---
echo "============================================================"
echo "  Instalação concluída com sucesso"
echo "============================================================"
echo ""
echo "Próximos passos (fazer como utilizador '$TARGET_USER'):"
echo ""
echo "  1. Recarregar o shell:"
echo "      source ~/.bashrc"
echo ""
echo "  2. Testar o fluxo de voz:"
echo "      voicevision-listen-and-copy"
echo "      xclip -selection clipboard -o"
echo ""
echo "  3. Configurar o hotkey global no Cinnamon:"
echo "      Menu → Preferências → Teclado → Atalhos → Personalizados"
echo "      Comando: $WRAPPER_DST"
echo "      Atalho: ex. F9 (ou outro que não conflite)"
echo ""
echo "  4. No OpenCode: focar o input, premir o hotkey, falar,"
echo "     colar com ctrl+v e revisar antes de enviar."
echo ""
echo "Documentação completa: docs/VOICE_INPUT.md"
echo ""
