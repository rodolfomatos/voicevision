"""Integration tests against real whisper.cpp subprocess.

These tests exercise voicevision against a real whisper.cpp binary, not a fake.
They are skipped if whisper-cli or the model are not available.

Run with:

    make test-integration   # runs tests marked 'integration'

Or directly:

    python -m pytest tests/backends/test_real_backends.py -m integration -v
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from voicevision.backends.whisper_cpp import WhisperCppBackend
from voicevision.server import ServerConfig, VoiceVisionService, create_server

# Models live in /models by default
MODELS_DIR = Path("/models")
WHISPER_MODEL = MODELS_DIR / "whisper-base.bin"

WHISPER_CLI = "/usr/local/bin/whisper-cli"

pytestmark = pytest.mark.integration


def _has_whisper() -> bool:
    return Path(WHISPER_CLI).exists() and WHISPER_MODEL.exists()


def _silent_wav() -> bytes:
    """1 second of silence as 16 kHz mono PCM16 WAV."""
    header = b"RIFF"
    header += (36 + 16000).to_bytes(4, "little")  # file size
    header += b"WAVE"
    header += b"fmt "
    header += (16).to_bytes(4, "little")  # subchunk size
    header += (1).to_bytes(2, "little")  # audio format (PCM)
    header += (1).to_bytes(2, "little")  # channels
    header += (16000).to_bytes(4, "little")  # sample rate
    header += (32000).to_bytes(4, "little")  # byte rate
    header += (2).to_bytes(2, "little")  # block align
    header += (16).to_bytes(2, "little")  # bits per sample
    header += b"data"
    header += (16000).to_bytes(4, "little")  # data size
    header += b"\x00" * 16000
    return header


class TestWhisperCppReal:
    """Real whisper.cpp backend tests. Skipped if whisper.cpp or model missing."""

    def test_backend_available(self) -> None:
        assert WhisperCppBackend.available()

    def test_transcribe_silence(self) -> None:
        if not _has_whisper():
            pytest.skip("whisper.cpp or model not available")
        backend = WhisperCppBackend(model=str(WHISPER_MODEL))
        result = backend.transcribe(_silent_wav())
        assert isinstance(result, str)
        assert isinstance(result, str)


class TestRealHTTPServer:
    """Real HTTP server tests with whisper.cpp backend."""

    def _make_config(self) -> Any:

        return ServerConfig(
            host="127.0.0.1",
            port=0,
            quiet=True,
            stt_model=str(WHISPER_MODEL) if WHISPER_MODEL.exists() else "",
            stt_language="en",
            llm_model="",
            llm_host="127.0.0.1",
            llm_port=8080,
            llm_max_tokens=512,
            vision_model="",
            vision_host="127.0.0.1",
            vision_port=8081,
            vision_backend="llama-cpp",
            emotion_enabled=False,
            speaker_enabled=False,
        )

    def test_health_endpoint(self) -> None:

        service = VoiceVisionService(self._make_config())
        server = create_server(service.config, service=service)

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            import urllib.request

            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_address[1]}/health", timeout=5
            )
            data = json.loads(resp.read())
            assert data["status"] == "ok"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_transcribe_endpoint(self) -> None:
        if not _has_whisper():
            pytest.skip("whisper.cpp not available")

        service = VoiceVisionService(self._make_config())
        server = create_server(service.config, service=service)

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            import base64
            import urllib.request

            wav = _silent_wav()
            payload = {"audio_base64": base64.b64encode(wav).decode(), "language": "pt"}
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.server_address[1]}/transcribe",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            assert "transcript" in data
            assert data.get("language") == "pt"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
