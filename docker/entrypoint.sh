#!/usr/bin/env bash
# voicevision container entrypoint.
#
# Two responsibilities:
#   1. Forward SIGTERM to the application so close() runs (ADR-003 §3).
#      Python as PID 1 ignores SIGTERM, so without this every graceful
#      shutdown is a 10-second hang followed by SIGKILL.
#   2. Fail early and legibly when the container is misconfigured.
#
# Compose sets `init: true`, so tini is PID 1 and does the signal forwarding
# and zombie reaping. This script is the child that installs the handler.

set -euo pipefail

term_handler() {
    echo "voicevision: SIGTERM received, shutting down" >&2
    if [[ -n "${APP_PID:-}" ]] && kill -0 "${APP_PID}" 2>/dev/null; then
        kill -TERM "${APP_PID}" 2>/dev/null || true
        # Give the app time to close its backends, then insist.
        for _ in $(seq 1 20); do
            kill -0 "${APP_PID}" 2>/dev/null || exit 0
            sleep 0.5
        done
        echo "voicevision: app did not exit in 10s, sending SIGKILL" >&2
        kill -KILL "${APP_PID}" 2>/dev/null || true
    fi
    exit 0
}

case "${1:-}" in
    voicevision-preflight)
        exec python3 -m voicevision.preflight "$@"
        ;;
    shell)
        exec /bin/bash "$@"
        ;;
esac

# Container sanity that shell can answer faster than Python.
if [[ ! -e /dev/snd && "${VOICEVISION_AUDIO_BACKEND:-}" == "sounddevice" ]]; then
    echo "voicevision: WARNING — VOICEVISION_AUDIO_BACKEND=sounddevice but /dev/snd" >&2
    echo "            is absent. Run the container with --device /dev/snd." >&2
fi

# Run the application in the background so the TERM trap can fire while it is
# the thing we are waiting on.
"$@" &
APP_PID=$!
trap term_handler TERM INT

wait "${APP_PID}"