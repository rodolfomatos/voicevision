"""Deterministic stand-in for a model executable.

Every behaviour a real model process can show is selectable via argv, so the
subprocess lifecycle is testable on a machine with no models installed. Uses the
real `Popen` path — mocking `subprocess` would test the mock, not the code.

Behaviours are chosen by the first positional argument to the script.
"""

from __future__ import annotations

import sys
import textwrap

# Behaviors this fake knows how to perform.
ECHO = "echo"
STDERR_FLOOD = "stderr-flood"
EXIT_NONZERO = "exit-nonzero"
SLEEP = "sleep"
BINARY = "binary"
DIE_MID_WRITE = "die-mid-write"
NOOP = "noop"

# whisper.cpp stand-ins
WHISPER_TRANSCRIPT = "whisper-transcript"
WHISPER_TIMESTAMPS = "whisper-timestamps"
WHISPER_EMPTY = "whisper-empty"
WHISPER_BLANK_AUDIO = "whisper-blank-audio"
WHISPER_TO_FILE = "whisper-to-file"
WHISPER_BAD_MODEL = "whisper-bad-model"
WHISPER_ECHO_WAV = "whisper-echo-wav"

_SCRIPT = textwrap.dedent(
    """
    import os, sys, time

    behavior = sys.argv[1]
    data = sys.stdin.buffer.read()

    if behavior == "echo":
        sys.stdout.buffer.write(data)
    elif behavior == "stderr-flood":
        # Write well past the 64 KiB pipe buffer before any stdout. A parent
        # that reads stdout while ignoring stderr blocks here forever.
        sys.stderr.buffer.write(b"E" * 200000)
        sys.stderr.buffer.flush()
        sys.stdout.buffer.write(b"survived")
    elif behavior == "exit-nonzero":
        sys.stderr.buffer.write(b"model exploded: bad weights\\n")
        sys.exit(3)
    elif behavior == "sleep":
        time.sleep(60)
    elif behavior == "binary":
        sys.stdout.buffer.write(bytes([0xFF, 0xFE, 0xFD, 0x00, 0x01]))
    elif behavior == "die-mid-write":
        sys.stdout.buffer.write(data[: len(data) // 2])
        sys.stdout.buffer.flush()
        # Hard exit without flushing, so the caller sees a truncated pipe.
        os._exit(9)
    elif behavior == "noop":
        pass
    elif behavior == "whisper-transcript":
        sys.stdout.buffer.write(b" hello there general kenobi ")
    elif behavior == "whisper-timestamps":
        # What whisper.cpp prints without -nt being honoured.
        sys.stdout.buffer.write(
            b"\\n[00:00:00.000 --> 00:00:02.500]   Hello there.\\n"
            b"[00:00:02.500 --> 00:00:05.000]   General Kenobi.\\n"
        )
    elif behavior == "whisper-empty":
        # Silence: a valid run with nothing recognised.
        sys.stdout.buffer.write(b"\\n\\n")
    elif behavior == "whisper-blank-audio":
        sys.stdout.buffer.write(b"[BLANK_AUDIO]\\n you are eating a shoe \\n")
    elif behavior == "whisper-to-file":
        # Some builds report the transcript file instead of writing to stdout.
        sys.stdout.buffer.write(b"\\n/transcript.txt\\n")
    elif behavior == "whisper-bad-model":
        sys.stderr.buffer.write(
            b"error: failed to open model file: unable to load model\\n"
        )
        sys.exit(1)
    elif behavior == "whisper-echo-wav":
        # Echo the stdin length so the test can prove the WAV arrived intact.
        sys.stdout.buffer.write(str(len(data)).encode())
    else:
        sys.stderr.buffer.write(b"unknown behavior: %s\\n" % behavior.encode())
        sys.exit(2)
    """
)


def build_argv(behavior: str, *, extra: list[str] | None = None) -> list[str]:
    """Argv for a fake child that performs `behavior`."""
    return [sys.executable, "-c", _SCRIPT, behavior, *(extra or [])]
