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
# Nota: atalhos globais do ambiente de desktop NÃO carregam ~/.bashrc, nem têm
# o PATH completo. Este script é autocontido para funcionar em qualquer contexto.
set -eu

# --- Garantir HOME está definido ---
export HOME="${HOME:-/home/rodolfo}"

# --- Garantir PATH completo (atalhos globais têm PATH limitado) ---
for p in "$HOME/.local/bin" /usr/local/bin /usr/bin /bin; do
    case ":$PATH:" in
        *:"$p":*) ;;
        *) export PATH="$p:$PATH" ;;
    esac
done

# --- Carregar variáveis de ambiente do ~/.bashrc (atalhos globais não o fazem) ---
if [ -f "$HOME/.bashrc" ]; then
    # shellcheck disable=SC1090
    . "$HOME/.bashrc" 2>/dev/null || true
fi

# --- Fallback: se a variável não ficou definida, usar valor padrão ---
export VOICEVISION_STT_MODEL="${VOICEVISION_STT_MODEL:-/models/whisper-base.bin}"
export VOICEVISION_STT_LANGUAGE="${VOICEVISION_STT_LANGUAGE:-pt}"

# --- Garantir DISPLAY para notify-send (X11) ---
export DISPLAY="${DISPLAY:-:0}"

TEXT=$(voicevision-listen --seconds 5 2>/dev/null || true)

if [ -z "$TEXT" ]; then
    notify-send "voicevision" "Nenhuma fala detetada" 2>/dev/null || true
    exit 0
fi

echo -n "$TEXT" | xclip -selection clipboard

notify-send "voicevision" "Transcrito: $TEXT" 2>/dev/null || true
