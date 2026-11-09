"""Tests for voicevision.server.

No real whisper, llama.cpp or moondream process is started. A fake service is
injected, so these tests exercise the HTTP contract — routing, validation,
auth, size limits and error mapping — without depending on model files.
"""

from __future__ import annotations

import base64
import json
import socket
import threading
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

from voicevision import __version__
from voicevision.audio import pcm16_to_wav
from voicevision.errors import BackendExecutionError, ConfigurationError
from voicevision.server import (
    MAX_BODY_BYTES,
    ServerConfig,
    VoiceVisionService,
    _BadRequest,
    _normalise_audio,
    create_server,
    load_config,
    main,
    serve,
)


class FakeService:
    """Drop-in replacement for VoiceVisionService with controllable failures."""

    def __init__(self) -> None:
        self.transcribed: list[tuple[bytes, str]] = []
        self.described: list[tuple[bytes, str]] = []
        self.conversed: list[tuple[str, int]] = []
        self.closed = False
        self.transcribe_error: Exception | None = None
        self.describe_error: Exception | None = None
        self.converse_error: Exception | None = None

    def transcribe(self, wav: bytes, language: str) -> tuple[str, float]:
        if self.transcribe_error is not None:
            raise self.transcribe_error
        self.transcribed.append((wav, language))
        return "hello world", 12.5

    def describe(self, image: bytes, question: str) -> str:
        if self.describe_error is not None:
            raise self.describe_error
        self.described.append((image, question))
        return "a cat on a mat"

    def converse(self, text: str, max_tokens: int) -> str:
        if self.converse_error is not None:
            raise self.converse_error
        self.conversed.append((text, max_tokens))
        return "the answer"

    def close(self) -> None:
        self.closed = True


def _config(**overrides: Any) -> ServerConfig:
    defaults: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": 0,
        "quiet": True,
        "stt_model": "/models/whisper-base.bin",
        "stt_language": "en",
        "llm_model": "/models/llm.gguf",
        "vision_model": "/models/vision.gguf",
        "max_body_bytes": 65536,
    }
    defaults.update(overrides)
    return ServerConfig(**defaults)


@pytest.fixture
def live() -> Iterator[tuple[Any, FakeService]]:
    """A bound server on an ephemeral port, serving in a background thread."""
    service = FakeService()
    server = create_server(_config(), service=service)  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, service
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _request(
    server: Any,
    method: str,
    path: str,
    body: Any = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    import http.client

    connection = http.client.HTTPConnection(
        "127.0.0.1",
        server.server_address[1],
        timeout=5,
    )
    try:
        if isinstance(body, dict):
            payload: bytes | None = json.dumps(body).encode("utf-8")
            headers = {"Content-Type": "application/json", **(headers or {})}
        else:
            payload = body
        connection.request(method, path, body=payload, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        return response.status, dict(response.getheaders()), raw
    finally:
        connection.close()


def _json(raw: bytes) -> Any:
    return json.loads(raw.decode("utf-8"))


def _audio_b64(pcm: bytes) -> str:
    return base64.b64encode(pcm).decode("ascii")


def _raw_request(server: Any, request: bytes, *, half_close: bool = False) -> bytes:
    with socket.create_connection(
        ("127.0.0.1", server.server_address[1]),
        timeout=5,
    ) as sock:
        sock.sendall(request)
        if half_close:
            sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    return b"".join(chunks)


class TestHealth:
    def test_health_returns_status_and_version(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, headers, body = _request(server, "GET", "/health")
        assert status == 200
        assert headers["Content-Type"].startswith("application/json")
        assert _json(body) == {"status": "ok", "version": __version__}

    def test_health_ignores_query_string(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(server, "GET", "/health?probe=1")
        assert status == 200
        assert _json(body)["status"] == "ok"

    def test_post_health_is_405(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, headers, body = _request(server, "POST", "/health", body={})
        assert status == 405
        assert headers["Allow"] == "GET"
        assert "not allowed" in _json(body)["error"]


class TestRouting:
    def test_unknown_path_is_404(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(server, "GET", "/nope")
        assert status == 404
        assert "unknown path" in _json(body)["error"]

    def test_get_transcribe_is_405(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, headers, body = _request(server, "GET", "/transcribe")
        assert status == 405
        assert headers["Allow"] == "POST"
        assert "not allowed" in _json(body)["error"]


class TestTranscribe:
    def test_raw_pcm_is_wrapped_as_wav(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        pcm = b"\x00\x01" * 1600
        status, _headers, body = _request(
            server,
            "POST",
            "/transcribe",
            body={"audio_base64": _audio_b64(pcm), "language": "pt"},
        )
        assert status == 200
        assert _json(body) == {
            "transcript": "hello world",
            "language": "pt",
            "transcription_ms": 12.5,
        }
        wav, language = service.transcribed[0]
        assert language == "pt"
        assert wav[:4] == b"RIFF"

    def test_wav_payload_is_passed_through(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        wav = pcm16_to_wav(b"\x00\x01" * 1600)
        status, _headers, _body = _request(
            server,
            "POST",
            "/transcribe",
            body={"audio_base64": _audio_b64(wav)},
        )
        assert status == 200
        assert service.transcribed[0][0] == wav

    def test_language_defaults_to_config(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        status, _headers, body = _request(
            server,
            "POST",
            "/transcribe",
            body={"audio_base64": _audio_b64(b"\x00\x00" * 100)},
        )
        assert status == 200
        assert _json(body)["language"] == "en"
        assert service.transcribed[0][1] == "en"

    def test_missing_audio_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(server, "POST", "/transcribe", body={})
        assert status == 400
        assert "audio_base64" in _json(body)["error"]

    def test_invalid_base64_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(
            server,
            "POST",
            "/transcribe",
            body={"audio_base64": "not base64!!"},
        )
        assert status == 400
        assert "base64" in _json(body)["error"]

    def test_empty_audio_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(
            server,
            "POST",
            "/transcribe",
            body={"audio_base64": ""},
        )
        assert status == 400
        assert "audio_base64" in _json(body)["error"]

    def test_odd_pcm_length_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(
            server,
            "POST",
            "/transcribe",
            body={"audio_base64": _audio_b64(b"\x00\x00\x00")},
        )
        assert status == 400
        assert "odd number" in _json(body)["error"]

    def test_invalid_wav_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        bogus = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"garbage"
        status, _headers, body = _request(
            server,
            "POST",
            "/transcribe",
            body={"audio_base64": _audio_b64(bogus)},
        )
        assert status == 400
        assert "WAV" in _json(body)["error"]

    def test_bad_language_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(
            server,
            "POST",
            "/transcribe",
            body={"audio_base64": _audio_b64(b"\x00\x00" * 100), "language": ""},
        )
        assert status == 400
        assert "language" in _json(body)["error"]

    def test_backend_failure_is_502(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        service.transcribe_error = BackendExecutionError("whispercpp", "boom")
        status, _headers, body = _request(
            server,
            "POST",
            "/transcribe",
            body={"audio_base64": _audio_b64(b"\x00\x00" * 100)},
        )
        assert status == 502
        assert "boom" in _json(body)["error"]

    def test_missing_configuration_is_500(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        service.transcribe_error = ConfigurationError("VOICEVISION_STT_MODEL is not set")
        status, _headers, body = _request(
            server,
            "POST",
            "/transcribe",
            body={"audio_base64": _audio_b64(b"\x00\x00" * 100)},
        )
        assert status == 500
        assert "VOICEVISION_STT_MODEL" in _json(body)["error"]


class TestDescribe:
    def test_describe_returns_description(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        image = b"\xff\xd8\xff\xe0fake-jpeg"
        status, _headers, body = _request(
            server,
            "POST",
            "/describe",
            body={"image_base64": _audio_b64(image), "question": "What is this?"},
        )
        assert status == 200
        assert _json(body) == {"description": "a cat on a mat"}
        assert service.described == [(image, "What is this?")]

    def test_default_question(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        status, _headers, _body = _request(
            server,
            "POST",
            "/describe",
            body={"image_base64": _audio_b64(b"image")},
        )
        assert status == 200
        assert service.described[0][1] == "Describe this image in detail."

    def test_missing_image_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(server, "POST", "/describe", body={})
        assert status == 400
        assert "image_base64" in _json(body)["error"]

    def test_bad_question_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(
            server,
            "POST",
            "/describe",
            body={"image_base64": _audio_b64(b"image"), "question": "  "},
        )
        assert status == 400
        assert "question" in _json(body)["error"]

    def test_backend_failure_is_502(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        service.describe_error = BackendExecutionError("moondream", "no server")
        status, _headers, body = _request(
            server,
            "POST",
            "/describe",
            body={"image_base64": _audio_b64(b"image")},
        )
        assert status == 502
        assert "no server" in _json(body)["error"]


class TestConverse:
    def test_converse_returns_response(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        status, _headers, body = _request(
            server,
            "POST",
            "/converse",
            body={"text": "hi", "max_tokens": 64},
        )
        assert status == 200
        assert _json(body) == {"response": "the answer"}
        assert service.conversed == [("hi", 64)]

    def test_max_tokens_defaults_to_config(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        status, _headers, _body = _request(
            server,
            "POST",
            "/converse",
            body={"text": "hi"},
        )
        assert status == 200
        assert service.conversed == [("hi", 512)]

    def test_missing_text_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(server, "POST", "/converse", body={})
        assert status == 400
        assert "text" in _json(body)["error"]

    @pytest.mark.parametrize("value", [0, -1, 8193, "many", True, None])
    def test_bad_max_tokens_is_400(
        self,
        live: tuple[Any, FakeService],
        value: Any,
    ) -> None:
        server, _service = live
        status, _headers, body = _request(
            server,
            "POST",
            "/converse",
            body={"text": "hi", "max_tokens": value},
        )
        assert status == 400
        assert "max_tokens" in _json(body)["error"]

    def test_backend_failure_is_502(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        service.converse_error = BackendExecutionError("llamacpp", "down")
        status, _headers, body = _request(
            server,
            "POST",
            "/converse",
            body={"text": "hi"},
        )
        assert status == 502
        assert "down" in _json(body)["error"]


class TestRequestValidation:
    def test_malformed_json_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(
            server,
            "POST",
            "/converse",
            body=b"{not json",
            headers={"Content-Type": "application/json"},
        )
        assert status == 400
        assert "malformed JSON" in _json(body)["error"]

    def test_json_array_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(
            server,
            "POST",
            "/converse",
            body=b"[1, 2, 3]",
            headers={"Content-Type": "application/json"},
        )
        assert status == 400
        assert "JSON object" in _json(body)["error"]

    def test_missing_content_length_is_411(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        raw = _raw_request(server, b"POST /converse HTTP/1.0\r\n\r\n")
        assert b" 411 " in raw
        assert b"Content-Length is required" in raw

    def test_oversized_body_is_413(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        status, _headers, body = _request(
            server,
            "POST",
            "/converse",
            body={"text": "x" * 100_000},
        )
        assert status == 413
        assert "exceeds" in _json(body)["error"]

    def test_invalid_content_length_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        raw = _raw_request(
            server,
            b"POST /converse HTTP/1.0\r\nContent-Length: abc\r\n\r\n",
        )
        assert b" 400 " in raw
        assert b"invalid Content-Length" in raw

    def test_negative_content_length_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        raw = _raw_request(
            server,
            b"POST /converse HTTP/1.0\r\nContent-Length: -1\r\n\r\n",
        )
        assert b" 400 " in raw
        assert b"invalid Content-Length" in raw

    def test_incomplete_body_is_400(self, live: tuple[Any, FakeService]) -> None:
        server, _service = live
        raw = _raw_request(
            server,
            b"POST /converse HTTP/1.0\r\nContent-Length: 100\r\n\r\nshort",
            half_close=True,
        )
        assert b" 400 " in raw
        assert b"incomplete request body" in raw

    def test_unexpected_exception_is_500(self, live: tuple[Any, FakeService]) -> None:
        server, service = live
        service.converse_error = RuntimeError("kaboom")
        status, _headers, body = _request(
            server,
            "POST",
            "/converse",
            body={"text": "hi"},
        )
        assert status == 500
        assert "internal error: kaboom" in _json(body)["error"]


class TestAuth:
    @pytest.fixture
    def secured(self) -> Iterator[tuple[Any, FakeService]]:
        service = FakeService()
        server = create_server(
            _config(token="s3cret"),  # type: ignore[arg-type]
            service=service,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server, service
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_missing_header_is_401(self, secured: tuple[Any, FakeService]) -> None:
        server, _service = secured
        status, headers, body = _request(server, "GET", "/health")
        assert status == 401
        assert headers["WWW-Authenticate"].startswith("Bearer")
        assert _json(body) == {"error": "unauthorized"}

    def test_wrong_token_is_401(self, secured: tuple[Any, FakeService]) -> None:
        server, _service = secured
        status, _headers, _body = _request(
            server,
            "GET",
            "/health",
            headers={"Authorization": "Bearer nope"},
        )
        assert status == 401

    def test_correct_token_is_accepted(self, secured: tuple[Any, FakeService]) -> None:
        server, _service = secured
        status, _headers, body = _request(
            server,
            "GET",
            "/health",
            headers={"Authorization": "Bearer s3cret"},
        )
        assert status == 200
        assert _json(body)["status"] == "ok"

    def test_auth_protects_endpoints(self, secured: tuple[Any, FakeService]) -> None:
        server, _service = secured
        status, _headers, _body = _request(
            server,
            "POST",
            "/converse",
            body={"text": "hi"},
        )
        assert status == 401


class TestService:
    def test_transcribe_requires_model(self) -> None:
        service = VoiceVisionService(ServerConfig())
        with pytest.raises(ConfigurationError, match="VOICEVISION_STT_MODEL"):
            service.transcribe(b"wav", "en")

    def test_describe_requires_model(self) -> None:
        service = VoiceVisionService(ServerConfig())
        with pytest.raises(ConfigurationError, match="VOICEVISION_VISION_MODEL"):
            service.describe(b"image", "what?")

    def test_converse_requires_model(self) -> None:
        service = VoiceVisionService(ServerConfig())
        with pytest.raises(ConfigurationError, match="VOICEVISION_LLM_MODEL"):
            service.converse("hi", 10)

    def test_transcribe_reuses_backend_per_language(self) -> None:
        created: list[Any] = []

        class FakeStt:
            def __init__(self, *, model: str, language: str) -> None:
                self.language = language
                self.closed = False
                created.append(self)

            def transcribe(self, wav: bytes) -> str:
                return f"text-{self.language}"

            def close(self) -> None:
                self.closed = True

        service = VoiceVisionService(_config())
        with patch("voicevision.server.WhisperCppBackend", FakeStt):
            first = service.transcribe(b"wav", "en")
            second = service.transcribe(b"wav", "en")
            third = service.transcribe(b"wav", "pt")

        assert first[0] == "text-en"
        assert second[0] == "text-en"
        assert third[0] == "text-pt"
        assert len(created) == 2

        service.close()
        assert all(backend.closed for backend in created)

    def test_describe_creates_moondream_backend(self) -> None:
        class FakeVision:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            def describe(self, image: bytes, prompt: str | None = None) -> str:
                return f"{prompt}:{image.decode('ascii')}"

        service = VoiceVisionService(_config())
        with patch("voicevision.server.MoondreamBackend", FakeVision):
            assert service.describe(b"img", "what") == "what:img"

    def test_converse_creates_llama_backend(self) -> None:
        class FakeCompletion:
            content = "answer"

        class FakeLlm:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = kwargs

            def complete(self, text: str, *, max_tokens: int = 512) -> FakeCompletion:
                return FakeCompletion()

            def close(self) -> None:
                pass

        service = VoiceVisionService(_config())
        with patch("voicevision.server.LlamaCppBackend", FakeLlm):
            assert service.converse("hi", 12) == "answer"
        service.close()

    def test_close_is_safe_when_nothing_was_created(self) -> None:
        VoiceVisionService(ServerConfig()).close()


class TestNormaliseAudio:
    def test_empty_audio_is_rejected(self) -> None:
        with pytest.raises(_BadRequest, match="empty"):
            _normalise_audio(b"")

    def test_raw_pcm_is_wrapped(self) -> None:
        assert _normalise_audio(b"\x00\x00").startswith(b"RIFF")

    def test_valid_wav_is_unchanged(self) -> None:
        wav = pcm16_to_wav(b"\x00\x00" * 10)
        assert _normalise_audio(wav) == wav


class TestConfig:
    def test_defaults(self) -> None:
        config = ServerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8765
        assert config.token == ""
        assert config.max_body_bytes == MAX_BODY_BYTES

    def test_load_config_reads_environment(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VOICEVISION_SERVER_HOST", "0.0.0.0")
        monkeypatch.setenv("VOICEVISION_SERVER_PORT", "9000")
        monkeypatch.setenv("VOICEVISION_SERVER_TOKEN", "tok")
        monkeypatch.setenv("VOICEVISION_STT_MODEL", "/models/w.bin")
        monkeypatch.setenv("VOICEVISION_STT_LANGUAGE", "pt")
        monkeypatch.setenv("VOICEVISION_LLM_MODEL", "/models/l.gguf")
        monkeypatch.setenv("VOICEVISION_LLM_PORT", "9090")
        monkeypatch.setenv("VOICEVISION_LLM_MAX_TOKENS", "256")
        monkeypatch.setenv("VOICEVISION_VISION_MODEL", "/models/v.gguf")
        monkeypatch.setenv("VOICEVISION_VISION_PORT", "9091")
        monkeypatch.setenv("VOICEVISION_QUIET", "1")

        config = load_config()
        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.token == "tok"
        assert config.stt_model == "/models/w.bin"
        assert config.stt_language == "pt"
        assert config.llm_model == "/models/l.gguf"
        assert config.llm_port == 9090
        assert config.llm_max_tokens == 256
        assert config.vision_model == "/models/v.gguf"
        assert config.vision_port == 9091
        assert config.quiet is True

    def test_load_config_ignores_invalid_numbers(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("VOICEVISION_SERVER_PORT", "not-a-number")
        monkeypatch.setenv("VOICEVISION_LLM_PORT", "also-bad")
        config = load_config()
        assert config.port == 8765
        assert config.llm_port == 8080


class TestServe:
    def test_bind_failure_returns_2(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def fail(_config: ServerConfig) -> Any:
            raise OSError("in use")

        monkeypatch.setattr("voicevision.server.create_server", fail)
        assert serve(ServerConfig(quiet=True)) == 2
        assert "could not bind" in capsys.readouterr().err

    def test_serve_shuts_down_on_keyboard_interrupt(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        closed: list[str] = []

        class FakeServer:
            server_address = ("127.0.0.1", 9999)
            app = FakeService()

            def serve_forever(self) -> None:
                raise KeyboardInterrupt

            def server_close(self) -> None:
                closed.append("server")

        monkeypatch.setattr(
            "voicevision.server.create_server",
            lambda _config: FakeServer(),
        )
        assert serve(ServerConfig(quiet=True)) == 0
        assert closed == ["server"]
        assert FakeServer.app.closed is True

    def test_request_logging_when_not_quiet(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        server = create_server(
            _config(quiet=False),  # type: ignore[arg-type]
            service=FakeService(),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            _request(server, "GET", "/health")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        assert "GET /health" in capsys.readouterr().err

    def test_serve_warns_when_exposed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        class FakeServer:
            server_address = ("0.0.0.0", 8765)
            app = FakeService()

            def serve_forever(self) -> None:
                raise KeyboardInterrupt

            def server_close(self) -> None:
                pass

        monkeypatch.setattr(
            "voicevision.server.create_server",
            lambda _config: FakeServer(),
        )
        serve(ServerConfig(host="0.0.0.0", token="tok"))
        err = capsys.readouterr().err
        assert "listening on http://0.0.0.0:8765" in err
        assert "reachable beyond localhost (bearer auth enabled)" in err


class TestMain:
    def test_main_passes_cli_overrides(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, ServerConfig] = {}

        def fake_serve(config: ServerConfig) -> int:
            captured["config"] = config
            return 0

        monkeypatch.setattr("voicevision.server.serve", fake_serve)
        monkeypatch.setattr(
            "sys.argv",
            [
                "voicevision-server",
                "--host",
                "0.0.0.0",
                "--port",
                "9001",
                "--token",
                "abc",
                "--quiet",
            ],
        )
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0
        config = captured["config"]
        assert config.host == "0.0.0.0"
        assert config.port == 9001
        assert config.token == "abc"
        assert config.quiet is True

    def test_main_uses_environment_when_no_flags(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, ServerConfig] = {}

        def fake_serve(config: ServerConfig) -> int:
            captured["config"] = config
            return 0

        monkeypatch.setenv("VOICEVISION_SERVER_PORT", "9100")
        monkeypatch.setattr("voicevision.server.serve", fake_serve)
        monkeypatch.setattr("sys.argv", ["voicevision-server"])
        with pytest.raises(SystemExit):
            main()
        assert captured["config"].port == 9100
