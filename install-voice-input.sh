#!/bin/sh
#
# install-voice-input.sh — instala dependências de sistema para voz → texto
#
# Uso:
#   sudo ./install-voice-input.sh
#
# O que faz:
#   1. Instala xclip (clipboard no X11)
#   2. Cria /models se não existir
#   3. Garante que ~/.local/bin/voicevision-listen-and-copy existe e é executável
#   4. Adiciona VOICEVISION_STT_MODEL / VOICEVISION_STT_LANGUAGE ao ~/.bashrc
#      (apenas se ainda não estiverem definidas)
#
# O que NÃO faz:
#   - Não constrói whisper.cpp (precisa de cmake + fonte do whisper.cpp)
#   - Não baixa modelos (o operador deve fornecer o ficheiro whisper-base.bin)
#   - Não configura hotkey global (feito na UI do Cinnamon)
#
# Sair em erro se algum comando falhar.
set -eu

echo "============================================================"
echo "  voicevision — instalador de dependências de voz → texto"
echo "============================================================"
echo ""

# --- 0. Detetar utilizador alvo (quem chamou o sudo) ---
TARGET_USER="${SUDO_USER:-$(whoami)}"
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
if [ -z "$TARGET_HOME" ]; then
    echo "Erro: não foi possível detetar o home do utilizador '$TARGET_USER'" >&2
    exit 1
fi

echo "Utilizador alvo: $TARGET_USER"
echo "Home: $TARGET_HOME"
echo ""

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
echo "Projeto: $PROJECT_ROOT"
echo ""

# --- 1. Instalar xclip ---
echo "[1/4] Instalando xclip (clipboard no X11)..."
if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y xclip
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y xclip
elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm xclip
else
    echo "Aviso: não foi possível detetar o gestor de pacotes. Instale xclip manualmente."
fi

if command -v xclip >/dev/null 2>&1; then
    echo "  ✓ xclip instalado: $(command -v xclip)"
else
    echo "  ✗ xclip não pôde ser instalado automaticamente."
fi
echo ""

# --- 2. Criar /models se não existir ---
echo "[2/4] Garantindo diretório /models..."
mkdir -p /models
chown "$TARGET_USER":"$TARGET_USER" /models 2>/dev/null || true
echo "  ✓ /models pronto (coloque aqui whisper-base.bin)"
echo ""

# --- 3. Garantir script wrapper em ~/.local/bin ---
echo "[3/4] Garantindo script wrapper em ~/.local/bin..."
WRAPPER_SRC="/opt/voicevision/scripts/voicevision-listen-and-copy.sh"
WRAPPER_DST="$TARGET_HOME/.local/bin/voicevision-listen-and-copy"

# O wrapper vive no projeto em scripts/voicevision-listen-and-copy.sh
WRAPPER_SRC="$PROJECT_ROOT/scripts/voicevision-listen-and-copy.sh"
if [ ! -f "$WRAPPER_SRC" ]; then
    echo "Aviso: $WRAPPER_SRC não encontrado — o wrapper não será instalado."
else
    install -m 0755 -o "$TARGET_USER" -g "$TARGET_USER" "$WRAPPER_SRC" "$WRAPPER_DST"
    echo "  ✓ wrapper instalado: $WRAPPER_DST"
fi

install -m 0755 -o "$TARGET_USER" -g "$TARGET_USER" "$WRAPPER_SRC" "$WRAPPER_DST"
echo "  ✓ wrapper instalado: $WRAPPER_DST"
echo ""

# --- 4. Adicionar variáveis de ambiente ao ~/.bashrc ---
echo "[4/4] Configurando variáveis de ambiente em ~/.bashrc..."
BASHRC="$TARGET_HOME/.bashrc"
touch "$BASHRC"
chown "$TARGET_USER":"$TARGET_USER" "$BASHRC" 2>/dev/null || true

if ! grep -q "VOICEVISION_STT_MODEL" "$BASHRC"; then
    cat >> "$BASHRC" <<'BASHRC_EOF'

# voicevision — configuração de STT (voz → texto)
# Ajuste o caminho do modelo conforme o ficheiro que baixar para /models
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
echo "  Instalação concluída"
echo "============================================================"
echo ""
echo "Próximos passos (fazer como utilizador '$TARGET_USER'):"
echo ""
echo "  1. Baixar um modelo whisper.cpp para /models, ex.:"
echo "      sudo cp whisper-base.bin /models/"
echo "      sudo chown $TARGET_USER:$TARGET_USER /models/whisper-base.bin"
echo ""
echo "  2. Recarregar o shell:"
echo "      source ~/.bashrc"
echo ""
echo "  3. Verificar que voicevision-listen está disponível:"
echo "      which voicevision-listen"
echo ""
echo "  4. Testar o fluxo de voz:"
echo "      voicevision-listen-and-copy"
echo "      xclip -selection clipboard -o"
echo ""
echo "  5. Configurar o hotkey global no Cinnamon:"
echo "      Menu → Preferências → Teclado → Atalhos → Personalizados"
echo "      Comando: $WRAPPER_DST"
echo "      Atalho: ex. F9 (ou outro que não conflite)"
echo ""
echo "  6. No OpenCode: focar o input, premir o hotkey, falar,"
echo "     colar com ctrl+v e revisar antes de enviar."
echo ""
echo "Aviso: whisper-cli e o ficheiro de modelo NÃO são instalados por"
echo "este script — deve obtê-los à parte (veja docs/VOICE_INPUT.md)."
echo ""
