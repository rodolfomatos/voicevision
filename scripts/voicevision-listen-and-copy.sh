#!/bin/sh
# voicevision-listen-and-copy — grava o microfone, transcreve, copia para o clipboard
#
# Fluxo:
#   1. pressiona o hotkey global
#   2. roda `voicevision-listen` (microfone → whisper.cpp → texto no stdout)
#   3. copia o texto para o clipboard (xclip)
#   4. no OpenCode, focas o input e colas com ctrl+v
#
# Requisitos:
#   - voicevision-listen no PATH (pip install -e . no voicevision)
#   - xclip
#   - VOICEVISION_STT_MODEL definido (export no ~/.bashrc)
set -eu

TEXT=$(voicevision-listen 2>/dev/null || true)

if [ -z "$TEXT" ]; then
    notify-send "voicevision" "Nenhuma fala detetada ou erro na transcrição" 2>/dev/null || true
    exit 0
fi

echo -n "$TEXT" | xclip -selection clipboard

notify-send "voicevision" "Transcrito: $TEXT" 2>/dev/null || true
