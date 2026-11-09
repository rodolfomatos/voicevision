"""Tests for voicevision.client.

The client is exercised against a real T035/T036 server started in a thread,
with a fake service. No model process is involved.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from voicevision.client import VoiceVisionClient, VoiceVisionClientError
from voicevision.errors import BackendExecutionError, ConfigurationError
from voicevision.server import ServerConfig, create_server


class FakeService:
    def __init__(self) -> None:
        self.transcribed: list[tuple[bytes, str]] = []
        self.described: list[tuple[bytes, str]] = []
        self.conversed: list[tuple[str, int]] = []
        self.streamed: list[tuple[str, int]] = []
        self.transcribe_error: Exception | None = None
        self.describe_error: Exception | None = None
        self.converse_error: Exception | None = None
        self.stream_error: Exception | None = None

    def transcribe(self, wav: bytes, language: str) -> tuple[str, float]:
        if self.transcribe_error is not None:
            raise self.transcribe_error
        self.transcribed.append((wav, language))
        return "hello world", 3.25

    def describe(self, image: bytes, question: str) -> str:
        if self.describe_error is not None:
            raise self.describe_error
        self.described.append((image, question))
        return "a red bicycle"

    def converse(self, text: str, max_tokens: int) -> str:
        if self.converse_error is not None:
            raise self.converse_error
        self.conversed.append((text, max_tokens))
        return "the answer"

    def converse_stream(self, text: str, max_tokens: int) -> Iterator[str]:
        if self.stream_error is not None:
            raise self.stream_error
        self.streamed.append((text, max_tokens))
        yield "Hello"
        yield " world"

    def close(self) -> None:
        pass


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


def _start(config: ServerConfig) -> tuple[Any, FakeService, threading.Thread]:
    service = FakeService()
    server = create_server(config, service=service)  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, service, thread


def _stop(server: Any, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture
def live() -> Iterator[tuple[VoiceVisionClient, FakeService]]:
    server, service, thread = _start(_config())
    client = VoiceVisionClient(f"http://127.0.0.1:{server.server_address[1]}")
    try:
        yield client, service
    finally:
        _stop(server, thread)


class TestHttp:
    def test_health(self, live: tuple[VoiceVisionClient, FakeService]) -> None:
        client, _service = live
        payload = client.health()
        assert payload["status"] == "ok"
        assert "version" in payload

    def test_transcribe(self, live: tuple[VoiceVisionClient, FakeService]) -> None:
        client, service = live
        payload = client.transcribe(b"\x00\x01" * 100, language="pt")
        assert payload["transcript"] == "hello world"
        assert payload["language"] == "pt"
        assert payload["transcription_ms"] == 3.25
        assert service.transcribed[0][1] == "pt"

    def test_transcribe_without_language(
        self,
        live: tuple[VoiceVisionClient, FakeService],
    ) -> None:
        client, service = live
        payload = client.transcribe(b"\x00\x01" * 100)
        assert payload["language"] == "en"
        assert service.transcribed[0][1] == "en"

    def test_describe(self, live: tuple[VoiceVisionClient, FakeService]) -> None:
        client, service = live
        payload = client.describe(b"\xff\xd8fake", question="What is it?")
        assert payload == {"description": "a red bicycle"}
        assert service.described == [(b"\xff\xd8fake", "What is it?")]

    def test_describe_without_question(
        self,
        live: tuple[VoiceVisionClient, FakeService],
    ) -> None:
        client, service = live
        client.describe(b"image")
        assert service.described[0][1] == "Describe this image in detail."

    def test_converse(self, live: tuple[VoiceVisionClient, FakeService]) -> None:
        client, service = live
        assert client.converse("hi", max_tokens=32) == {"response": "the answer"}
        assert service.conversed == [("hi", 32)]

    def test_converse_without_max_tokens(
        self,
        live: tuple[VoiceVisionClient, FakeService],
    ) -> None:
        client, service = live
        client.converse("hi")
        assert service.conversed == [("hi", 512)]


class TestErrors:
    def test_backend_error_keeps_server_message(
        self,
        live: tuple[VoiceVisionClient, FakeService],
    ) -> None:
        client, service = live
        service.converse_error = BackendExecutionError("llamacpp", "model is down")
        with pytest.raises(VoiceVisionClientError, match="HTTP 502: .*model is down"):
            client.converse("hi")

    def test_configuration_error_is_reported(
        self,
        live: tuple[VoiceVisionClient, FakeService],
    ) -> None:
        client, service = live
        service.transcribe_error = ConfigurationError("VOICEVISION_STT_MODEL is not set")
        with pytest.raises(VoiceVisionClientError, match="VOICEVISION_STT_MODEL"):
            client.transcribe(b"\x00\x00" * 10)

    def test_unreachable_server(self) -> None:
        client = VoiceVisionClient("http://127.0.0.1:1", timeout=1.0)
        with pytest.raises(VoiceVisionClientError, match="cannot reach"):
            client.health()

    def test_invalid_base_url(self) -> None:
        with pytest.raises(ValueError, match="http"):
            VoiceVisionClient("127.0.0.1:8765")

    def test_invalid_timeout(self) -> None:
        with pytest.raises(ValueError, match="timeout"):
            VoiceVisionClient(timeout=0)


class TestAuth:
    def test_token_is_sent(self) -> None:
        server, _service, thread = _start(_config(token="s3cret"))
        client = VoiceVisionClient(
            f"http://127.0.0.1:{server.server_address[1]}",
            token="s3cret",
        )
        try:
            assert client.health()["status"] == "ok"
        finally:
            _stop(server, thread)

    def test_missing_token_is_reported(self) -> None:
        server, _service, thread = _start(_config(token="s3cret"))
        client = VoiceVisionClient(f"http://127.0.0.1:{server.server_address[1]}")
        try:
            with pytest.raises(VoiceVisionClientError, match="HTTP 401: unauthorized"):
                client.health()
        finally:
            _stop(server, thread)


class TestStream:
    def test_stream_yields_transcript_and_tokens(
        self,
        live: tuple[VoiceVisionClient, FakeService],
    ) -> None:
        client, service = live
        messages = list(client.stream([b"\x00\x01" * 100], language="pt"))
        assert [message["type"] for message in messages] == [
            "transcript",
            "token",
            "token",
            "done",
        ]
        assert messages[0]["transcript"] == "hello world"
        assert messages[0]["language"] == "pt"
        assert messages[1] == {"type": "token", "text": "Hello"}
        assert messages[2] == {"type": "token", "text": " world"}
        assert service.streamed == [("hello world", 512)]

    def test_stream_without_language(
        self,
        live: tuple[VoiceVisionClient, FakeService],
    ) -> None:
        client, service = live
        list(client.stream([b"\x00\x01" * 100]))
        assert service.transcribed[0][1] == "en"

    def test_stream_error_is_yielded_then_stops(
        self,
        live: tuple[VoiceVisionClient, FakeService],
    ) -> None:
        client, service = live
        service.stream_error = ConfigurationError("VOICEVISION_LLM_MODEL is not set")
        messages = list(client.stream([b"\x00\x01" * 100]))
        assert messages[0]["type"] == "transcript"
        assert messages[-1]["type"] == "error"
        assert "VOICEVISION_LLM_MODEL" in messages[-1]["error"]

    def test_stream_with_token(self) -> None:
        server, _service, thread = _start(_config(token="s3cret"))
        client = VoiceVisionClient(
            f"http://127.0.0.1:{server.server_address[1]}",
            token="s3cret",
        )
        try:
            messages = list(client.stream([b"\x00\x01" * 100]))
            assert messages[-1] == {"type": "done"}
        finally:
            _stop(server, thread)

    def test_stream_without_token_is_rejected(self) -> None:
        server, _service, thread = _start(_config(token="s3cret"))
        client = VoiceVisionClient(f"http://127.0.0.1:{server.server_address[1]}")
        try:
            with pytest.raises(VoiceVisionClientError, match="HTTP 401"):
                list(client.stream([b"\x00\x01" * 100]))
        finally:
            _stop(server, thread)


class TestErrorExtraction:
    def test_non_json_http_error_falls_back(self) -> None:
        import urllib.error

        exc = urllib.error.HTTPError(
            "http://x",
            503,
            "Service Unavailable",
            {},
            None,  # type: ignore[arg-type]
        )
        assert (
            VoiceVisionClient._http_error_message(exc)
            == "HTTP 503: Service Unavailable"
        )

    def test_json_error_without_error_field_falls_back(self) -> None:
        import io
        import urllib.error

        exc = urllib.error.HTTPError(
            "http://x",
            400,
            "Bad Request",
            {},
            io.BytesIO(json.dumps({"detail": "nope"}).encode("utf-8")),
        )
        assert VoiceVisionClient._http_error_message(exc) == "HTTP 400: Bad Request"


def test_health_rejects_non_object_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """A server returning a JSON array is a protocol violation, not a result."""

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"[1, 2, 3]"

    monkeypatch.setattr(
        "voicevision.client.urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    client = VoiceVisionClient()
    with pytest.raises(VoiceVisionClientError, match="non-object"):
        client.health()


def test_health_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"{not json"

    monkeypatch.setattr(
        "voicevision.client.urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    client = VoiceVisionClient()
    with pytest.raises(VoiceVisionClientError, match="invalid JSON"):
        client.health()
