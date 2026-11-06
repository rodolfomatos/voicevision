#!/bin/sh
# voicevision-listen-and-copy — grava o microfone, transcreve, copia para o clipboard
#
# Fluxo:
#   1. pressiona o hotkey global (Cinnamon ou linha de comandos)
#   2. roda `voicevision-listen --seconds 5` (grava 5s, transcreve via whisper.cpp)
#   3. copia o texto para o clipboard (xclip)
#   4. no OpenCode, focas o input e colas com ctrl+v
#
# Requisitos:
#   - voicevision-listen no PATH (pip install -e . no voicevision)
#   - xclip
#   - VOICEVISION_STT_MODEL definido
#
# Nota: este script é autocontido para funcionar tanto a partir de um terminal
# como de um atalho global do ambiente de desktop (que não carrega ~/.bashrc).
set -eu

# --- Garantir que ~/.local/bin está no PATH (para encontrar voicevision-listen) ---
case ":$PATH:" in
    *:"$HOME/.local/bin":*) ;;
    *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

# --- Carregar variáveis de ambiente do ~/.bashrc (não é feito por atalhos globais) ---
if [ -f "$HOME/.bashrc" ]; then
    # shellcheck disable=SC1090
    . "$HOME/.bashrc" 2>/dev/null || true
fi

# --- Garantir que DISPLAY está definido para notify-send (X11) ---
export DISPLAY="${DISPLAY:-:0}"

TEXT=$(voicevision-listen --seconds 5 2>/dev/null || true)

if [ -z "$TEXT" ]; then
    notify-send "voicevision" "Nenhuma fala detetada" 2>/dev/null || true
    exit 0
fi

echo -n "$TEXT" | xclip -selection clipboard

notify-send "voicevision" "Transcrito: $TEXT" 2>/dev/null || true
