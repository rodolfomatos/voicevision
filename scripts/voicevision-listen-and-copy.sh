#!/bin/sh
# voicevision-listen-and-copy — record microphone, transcribe, copy to clipboard
#
# Flow:
#   1. press the global hotkey (Cinnamon or command line)
#   2. run `voicevision-listen` (VAD detects speech, transcribes via whisper.cpp,
#      stops automatically after VOICEVISION_VAD_SILENCE_MS of silence)
#   3. copy the text to the clipboard (xclip)
#   4. in OpenCode, focus the input and paste with ctrl+v
#
# Requirements:
#   - voicevision-listen on PATH (pip install -e . in voicevision)
#   - xclip
#   - VOICEVISION_STT_MODEL set
#
# Note: global desktop shortcuts do NOT load ~/.bashrc and have a limited PATH.
# This script is self-contained to work in any context.
set -eu

# --- Ensure HOME is defined ---
export HOME="${HOME:-/home/rodolfo}"

# --- Ensure full PATH (global shortcuts have a restricted PATH) ---
for p in "$HOME/.local/bin" /usr/local/bin /usr/bin /bin; do
    case ":$PATH:" in
        *:"$p":*) ;;
        *) export PATH="$p:$PATH" ;;
    esac
done

# --- Load environment variables from ~/.bashrc (global shortcuts don't) ---
if [ -f "$HOME/.bashrc" ]; then
    # shellcheck disable=SC1090
    . "$HOME/.bashrc" 2>/dev/null || true
fi

# --- Fallback defaults if variables were not defined ---
export VOICEVISION_STT_MODEL="${VOICEVISION_STT_MODEL:-/models/whisper-base.bin}"
export VOICEVISION_STT_LANGUAGE="${VOICEVISION_STT_LANGUAGE:-pt}"
export VOICEVISION_VAD_SILENCE_MS="${VOICEVISION_VAD_SILENCE_MS:-2000}"
export VOICEVISION_VAD_AGGRESSIVENESS="${VOICEVISION_VAD_AGGRESSIVENESS:-2}"
export VOICEVISION_MAX_RECORD_SECONDS="${VOICEVISION_MAX_RECORD_SECONDS:-60}"

# --- Ensure DISPLAY for notify-send (X11) ---
export DISPLAY="${DISPLAY:-:0}"

TEXT=$(voicevision-listen 2>/dev/null || true)

if [ -z "$TEXT" ]; then
    notify-send "voicevision" "No speech detected" 2>/dev/null || true
    exit 0
fi

echo -n "$TEXT" | xclip -selection clipboard

notify-send "voicevision" "Transcribed: $TEXT" 2>/dev/null || true
