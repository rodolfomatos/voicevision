"""Tests for the WebSocket codec and the `/stream` endpoint.

The endpoint is exercised through a real socket: handshake, masked frames,
control frames, close codes and JSON messages. A fake service means no model
process is needed.
"""

from __future__ import annotations

import base64
import io
import json
import socket
import struct
import threading
from collections.abc import Iterator
from typing import Any

import pytest

from voicevision.errors import BackendExecutionError, ConfigurationError
from voicevision.server import ServerConfig, VoiceVisionService, create_server
from voicevision.websocket import (
    CLOSE_INVALID_DATA,
    CLOSE_NORMAL,
    CLOSE_PROTOCOL_ERROR,
    CLOSE_TOO_BIG,
    CLOSE_UNSUPPORTED,
    OPCODE_BINARY,
    OPCODE_CLOSE,
    OPCODE_PING,
    OPCODE_PONG,
    OPCODE_TEXT,
    WebSocketClosed,
    WebSocketProtocolError,
    accept_key,
    encode_close,
    encode_frame,
    read_frame,
)


def _masked_frame(
    opcode: int,
    payload: bytes,
    *,
    fin: bool = True,
    mask: bytes = b"\x01\x02\x03\x04",
    rsv: int = 0,
) -> bytes:
    first = (0x80 if fin else 0) | rsv | opcode
    length = len(payload)
    header = bytearray([first])
    if length < 126:
        header.append(0x80 | length)
    elif length <= 0xFFFF:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    header.extend(mask)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes(header) + masked


class TestAcceptKey:
    def test_rfc6455_example(self) -> None:
        assert accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


class TestFrameCodec:
    def test_short_text_frame_roundtrip(self) -> None:
        frame = read_frame(io.BytesIO(_masked_frame(OPCODE_TEXT, b"hello")))
        assert frame.opcode == OPCODE_TEXT
        assert frame.payload == b"hello"
        assert frame.fin is True

    def test_medium_length_roundtrip(self) -> None:
        payload = b"x" * 300
        frame = read_frame(io.BytesIO(_masked_frame(OPCODE_TEXT, payload)))
        assert frame.payload == payload

    def test_long_length_roundtrip(self) -> None:
        payload = b"x" * 70_000
        frame = read_frame(io.BytesIO(_masked_frame(OPCODE_TEXT, payload)))
        assert frame.payload == payload

    def test_server_frame_is_unmasked(self) -> None:
        encoded = encode_frame(b"hi")
        assert encoded[0] == 0x81
        assert encoded[1] & 0x80 == 0
        assert encoded[2:] == b"hi"

    def test_long_server_frame_uses_64bit_length(self) -> None:
        encoded = encode_frame(b"x" * 70_000)
        assert encoded[0] == 0x81
        assert encoded[1] == 127
        assert len(encoded) == 10 + 70_000

    def test_close_frame_encodes_code_and_reason(self) -> None:
        encoded = encode_close(CLOSE_NORMAL, "bye")
        frame = read_frame(io.BytesIO(_masked_frame(OPCODE_CLOSE, encoded[2:])))
        assert frame.opcode == OPCODE_CLOSE
        assert struct.unpack("!H", frame.payload[:2])[0] == CLOSE_NORMAL
        assert frame.payload[2:] == b"bye"

    def test_unmasked_client_frame_is_rejected(self) -> None:
        raw = bytes([0x81, 2]) + b"hi"
        with pytest.raises(WebSocketProtocolError) as excinfo:
            read_frame(io.BytesIO(raw))
        assert excinfo.value.code == CLOSE_PROTOCOL_ERROR

    def test_rsv_bits_are_rejected(self) -> None:
        raw = _masked_frame(OPCODE_TEXT, b"hi", rsv=0x40)
        with pytest.raises(WebSocketProtocolError) as excinfo:
            read_frame(io.BytesIO(raw))
        assert excinfo.value.code == CLOSE_PROTOCOL_ERROR

    def test_fragmentation_is_rejected(self) -> None:
        raw = _masked_frame(OPCODE_TEXT, b"hi", fin=False)
        with pytest.raises(WebSocketProtocolError) as excinfo:
            read_frame(io.BytesIO(raw))
        assert excinfo.value.code == CLOSE_UNSUPPORTED

    def test_fragmented_control_frame_is_rejected(self) -> None:
        raw = _masked_frame(OPCODE_PING, b"hi", fin=False)
        with pytest.raises(WebSocketProtocolError) as excinfo:
            read_frame(io.BytesIO(raw))
        assert excinfo.value.code == CLOSE_PROTOCOL_ERROR

    def test_oversized_control_frame_is_rejected(self) -> None:
        raw = _masked_frame(OPCODE_PING, b"x" * 126)
        with pytest.raises(WebSocketProtocolError) as excinfo:
            read_frame(io.BytesIO(raw))
        assert excinfo.value.code == CLOSE_PROTOCOL_ERROR

    def test_oversized_data_frame_is_rejected(self) -> None:
        raw = _masked_frame(OPCODE_TEXT, b"x" * 200)
        with pytest.raises(WebSocketProtocolError) as excinfo:
            read_frame(io.BytesIO(raw), max_payload=100)
        assert excinfo.value.code == CLOSE_TOO_BIG

    def test_truncated_frame_raises_closed(self) -> None:
        raw = bytes([0x81, 0x85]) + b"\x00\x00\x00\x00" + b"hi"
        with pytest.raises(WebSocketClosed):
            read_frame(io.BytesIO(raw))


class FakeStreamingService:
    """Fake service for /stream: fixed transcript and two token chunks."""

    def __init__(self) -> None:
        self.transcribed: list[tuple[bytes, str]] = []
        self.streamed: list[tuple[str, int]] = []
        self.closed = False
        self.transcribe_error: Exception | None = None
        self.stream_error: Exception | None = None

    def transcribe(self, wav: bytes, language: str) -> tuple[str, float]:
        if self.transcribe_error is not None:
            raise self.transcribe_error
        self.transcribed.append((wav, language))
        return "hello world", 7.5

    def converse_stream(self, text: str, max_tokens: int) -> Iterator[str]:
        if self.stream_error is not None:
            raise self.stream_error
        self.streamed.append((text, max_tokens))
        yield "Hello"
        yield " world"

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
def live() -> Iterator[tuple[Any, FakeStreamingService]]:
    service = FakeStreamingService()
    server = create_server(_config(), service=service)  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, service
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("socket closed")
        data.extend(chunk)
    return bytes(data)


def _recv_until(sock: socket.socket, marker: bytes) -> bytes:
    data = bytearray()
    while marker not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


class WSClient:
    """Minimal test client: masked frames out, unmasked frames in."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock

    def send_raw(self, opcode: int, payload: bytes, *, mask: bool = True) -> None:
        if mask:
            self.sock.sendall(_masked_frame(opcode, payload))
        else:
            length = len(payload)
            self.sock.sendall(bytes([0x80 | opcode, length]) + payload)

    def send_text(self, message: dict[str, Any]) -> None:
        self.send_raw(OPCODE_TEXT, json.dumps(message).encode("utf-8"))

    def recv(self) -> tuple[int, bytes]:
        first, second = _recv_exact(self.sock, 2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", _recv_exact(self.sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", _recv_exact(self.sock, 8))[0]
        assert second & 0x80 == 0, "server frames must not be masked"
        return opcode, _recv_exact(self.sock, length)

    def recv_json(self) -> dict[str, Any]:
        opcode, payload = self.recv()
        assert opcode == OPCODE_TEXT
        return json.loads(payload)

    def close(self) -> None:
        self.sock.close()


def _handshake(
    server: Any,
    *,
    path: str = "/stream",
    key: str | None = "dGhlIHNhbXBsZSBub25jZQ==",
    version: str = "13",
    upgrade: bool = True,
    headers: dict[str, str] | None = None,
) -> tuple[socket.socket, bytes]:
    sock = socket.create_connection(
        ("127.0.0.1", server.server_address[1]),
        timeout=5,
    )
    lines = [
        f"GET {path} HTTP/1.1",
        f"Host: 127.0.0.1:{server.server_address[1]}",
    ]
    if upgrade:
        lines.append("Upgrade: websocket")
        lines.append("Connection: Upgrade")
    if key is not None:
        lines.append(f"Sec-WebSocket-Key: {key}")
    if version:
        lines.append(f"Sec-WebSocket-Version: {version}")
    for name, value in (headers or {}).items():
        lines.append(f"{name}: {value}")
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
    return sock, _recv_until(sock, b"\r\n\r\n")


def _status(response: bytes) -> int:
    return int(response.split(b" ", 2)[1])


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class TestHandshake:
    def test_valid_upgrade(self, live: tuple[Any, FakeStreamingService]) -> None:
        server, _service = live
        sock, response = _handshake(server)
        try:
            assert _status(response) == 101
            assert b"Upgrade: websocket" in response
            assert b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=" in response
        finally:
            sock.close()

    def test_missing_key_is_400(self, live: tuple[Any, FakeStreamingService]) -> None:
        server, _service = live
        sock, response = _handshake(server, key=None)
        try:
            assert _status(response) == 400
        finally:
            sock.close()

    def test_wrong_version_is_426(self, live: tuple[Any, FakeStreamingService]) -> None:
        server, _service = live
        sock, response = _handshake(server, version="12")
        try:
            assert _status(response) == 426
            assert b"Sec-WebSocket-Version: 13" in response
        finally:
            sock.close()

    def test_missing_upgrade_is_400(self, live: tuple[Any, FakeStreamingService]) -> None:
        server, _service = live
        sock, response = _handshake(server, upgrade=False)
        try:
            assert _status(response) == 400
        finally:
            sock.close()

    def test_auth_required(self) -> None:
        service = FakeStreamingService()
        server = create_server(_config(token="secret"), service=service)  # type: ignore[arg-type]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            sock, response = _handshake(server)
            try:
                assert _status(response) == 401
            finally:
                sock.close()

            sock, response = _handshake(
                server,
                headers={"Authorization": "Bearer secret"},
            )
            try:
                assert _status(response) == 101
            finally:
                sock.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


class TestStreaming:
    def _client(self, server: Any) -> WSClient:
        sock, response = _handshake(server)
        assert _status(response) == 101
        return WSClient(sock)

    def test_audio_then_end_streams_transcript_and_tokens(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, service = live
        client = self._client(server)
        try:
            client.send_text(
                {
                    "type": "audio",
                    "audio_base64": _b64(b"\x00\x01" * 1600),
                    "language": "pt",
                }
            )
            client.send_text({"type": "end"})

            transcript = client.recv_json()
            assert transcript["type"] == "transcript"
            assert transcript["transcript"] == "hello world"
            assert transcript["language"] == "pt"
            assert transcript["transcription_ms"] == 7.5

            assert client.recv_json() == {"type": "token", "text": "Hello"}
            assert client.recv_json() == {"type": "token", "text": " world"}
            assert client.recv_json() == {"type": "done"}

            assert service.transcribed[0][0][:4] == b"RIFF"
            assert service.streamed == [("hello world", 512)]
        finally:
            client.close()

    def test_multiple_audio_chunks_are_concatenated(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, service = live
        client = self._client(server)
        try:
            client.send_text({"type": "audio", "audio_base64": _b64(b"\x00\x01" * 100)})
            client.send_text({"type": "audio", "audio_base64": _b64(b"\x00\x02" * 100)})
            client.send_text({"type": "end"})
            assert client.recv_json()["type"] == "transcript"
            client.recv_json()
            client.recv_json()
            assert client.recv_json()["type"] == "done"
            assert len(service.transcribed[0][0]) > 400
        finally:
            client.close()

    def test_reset_discards_audio(self, live: tuple[Any, FakeStreamingService]) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.send_text({"type": "audio", "audio_base64": _b64(b"\x00\x01" * 100)})
            client.send_text({"type": "reset"})
            client.send_text({"type": "end"})
            assert client.recv_json() == {"type": "error", "error": "no audio received"}
        finally:
            client.close()

    def test_language_defaults_to_config(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, service = live
        client = self._client(server)
        try:
            client.send_text({"type": "audio", "audio_base64": _b64(b"\x00\x01" * 100)})
            client.send_text({"type": "end"})
            assert client.recv_json()["language"] == "en"
            assert service.transcribed[0][1] == "en"
        finally:
            client.close()

    def test_ping_gets_pong(self, live: tuple[Any, FakeStreamingService]) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.send_raw(OPCODE_PING, b"ping")
            assert client.recv() == (OPCODE_PONG, b"ping")
        finally:
            client.close()

    def test_pong_is_ignored(self, live: tuple[Any, FakeStreamingService]) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.send_raw(OPCODE_PONG, b"unsolicited")
            client.send_raw(OPCODE_PING, b"still-here")
            assert client.recv() == (OPCODE_PONG, b"still-here")
        finally:
            client.close()

    def test_abrupt_disconnect_is_handled(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, _service = live
        client = self._client(server)
        client.sock.sendall(b"\x81")
        client.close()

        # The server must still accept a new connection after the half-frame.
        sock, response = _handshake(server)
        try:
            assert _status(response) == 101
        finally:
            sock.close()

    def test_client_close_is_echoed(self, live: tuple[Any, FakeStreamingService]) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.send_raw(OPCODE_CLOSE, struct.pack("!H", CLOSE_NORMAL))
            opcode, payload = client.recv()
            assert opcode == OPCODE_CLOSE
            assert struct.unpack("!H", payload[:2])[0] == CLOSE_NORMAL
        finally:
            client.close()

    def test_malformed_json_is_recoverable(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.send_raw(OPCODE_TEXT, b"{not json")
            assert client.recv_json() == {"type": "error", "error": "malformed JSON"}
            client.send_text({"type": "end"})
            assert client.recv_json() == {"type": "error", "error": "no audio received"}
        finally:
            client.close()

    def test_non_object_json_is_recoverable(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.send_raw(OPCODE_TEXT, b"[1, 2]")
            assert client.recv_json() == {
                "type": "error",
                "error": "message must be a JSON object",
            }
        finally:
            client.close()

    def test_unknown_type_is_recoverable(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.send_text({"type": "nope"})
            assert "unknown message type" in client.recv_json()["error"]
        finally:
            client.close()

    def test_invalid_base64_is_recoverable(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.send_text({"type": "audio", "audio_base64": "not base64!!"})
            assert "base64" in client.recv_json()["error"]
        finally:
            client.close()

    def test_backend_failure_is_reported(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, service = live
        service.transcribe_error = BackendExecutionError("whispercpp", "boom")
        client = self._client(server)
        try:
            client.send_text({"type": "audio", "audio_base64": _b64(b"\x00\x01" * 100)})
            client.send_text({"type": "end"})
            message = client.recv_json()
            assert message["type"] == "error"
            assert "boom" in message["error"]
        finally:
            client.close()

    def test_stream_configuration_error_is_reported(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, service = live
        service.stream_error = ConfigurationError("VOICEVISION_LLM_MODEL is not set")
        client = self._client(server)
        try:
            client.send_text({"type": "audio", "audio_base64": _b64(b"\x00\x01" * 100)})
            client.send_text({"type": "end"})
            assert client.recv_json()["type"] == "transcript"
            message = client.recv_json()
            assert message["type"] == "error"
            assert "VOICEVISION_LLM_MODEL" in message["error"]
        finally:
            client.close()

    def test_stream_backend_error_is_reported(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, service = live
        service.stream_error = BackendExecutionError("llamacpp", "down")
        client = self._client(server)
        try:
            client.send_text({"type": "audio", "audio_base64": _b64(b"\x00\x01" * 100)})
            client.send_text({"type": "end"})
            assert client.recv_json()["type"] == "transcript"
            assert "down" in client.recv_json()["error"]
        finally:
            client.close()

    def test_stream_unexpected_error_is_reported(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, service = live
        service.stream_error = RuntimeError("kaboom")
        client = self._client(server)
        try:
            client.send_text({"type": "audio", "audio_base64": _b64(b"\x00\x01" * 100)})
            client.send_text({"type": "end"})
            assert client.recv_json()["type"] == "transcript"
            assert "internal error: kaboom" in client.recv_json()["error"]
        finally:
            client.close()


class TestProtocolViolations:
    def _client(self, server: Any) -> WSClient:
        sock, response = _handshake(server)
        assert _status(response) == 101
        return WSClient(sock)

    def _close_code(self, client: WSClient) -> int:
        opcode, payload = client.recv()
        assert opcode == OPCODE_CLOSE
        return struct.unpack("!H", payload[:2])[0]

    def test_unmasked_frame_closes_1002(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.send_raw(OPCODE_TEXT, b"{}", mask=False)
            assert self._close_code(client) == CLOSE_PROTOCOL_ERROR
        finally:
            client.close()

    def test_fragmented_frame_closes_1003(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.sock.sendall(_masked_frame(OPCODE_TEXT, b"{}", fin=False))
            assert self._close_code(client) == CLOSE_UNSUPPORTED
        finally:
            client.close()

    def test_binary_frame_closes_1003(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.send_raw(OPCODE_BINARY, b"\x00\x01")
            assert self._close_code(client) == CLOSE_UNSUPPORTED
        finally:
            client.close()

    def test_invalid_utf8_closes_1007(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, _service = live
        client = self._client(server)
        try:
            client.send_raw(OPCODE_TEXT, b"\xff\xfe")
            assert self._close_code(client) == CLOSE_INVALID_DATA
        finally:
            client.close()

    def test_oversized_frame_closes_1009(
        self,
        live: tuple[Any, FakeStreamingService],
    ) -> None:
        server, _service = live
        client = self._client(server)
        try:
            # Declared length above the 1 MiB frame cap; the codec rejects it
            # before reading a mask or payload.
            header = bytes([0x81, 0x80 | 127]) + struct.pack("!Q", 2 * 1024 * 1024)
            client.sock.sendall(header)
            assert self._close_code(client) == CLOSE_TOO_BIG
        finally:
            client.close()


class TestAudioCap:
    def test_exceeding_buffer_cap_clears_audio(self) -> None:
        service = FakeStreamingService()
        server = create_server(
            _config(max_body_bytes=1000),  # type: ignore[arg-type]
            service=service,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            sock, response = _handshake(server)
            assert _status(response) == 101
            client = WSClient(sock)
            try:
                client.send_text(
                    {"type": "audio", "audio_base64": _b64(b"\x00\x01" * 300)}
                )
                client.send_text(
                    {"type": "audio", "audio_base64": _b64(b"\x00\x01" * 300)}
                )
                message = client.recv_json()
                assert message["type"] == "error"
                assert "exceeds" in message["error"]
                client.send_text({"type": "end"})
                assert client.recv_json() == {
                    "type": "error",
                    "error": "no audio received",
                }
            finally:
                client.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


class TestServiceStreaming:
    def test_converse_stream_requires_model(self) -> None:
        service = VoiceVisionService(ServerConfig())
        with pytest.raises(ConfigurationError, match="VOICEVISION_LLM_MODEL"):
            list(service.converse_stream("hi", 10))

    def test_converse_stream_yields_backend_chunks(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        created: list[Any] = []

        class FakeLlm:
            def __init__(self, **kwargs: Any) -> None:
                created.append(self)

            def complete_stream(self, text: str, *, max_tokens: int = 512) -> Iterator[str]:
                yield f"{text}:{max_tokens}"

            def close(self) -> None:
                pass

        service = VoiceVisionService(_config())
        monkeypatch.setattr("voicevision.server.LlamaCppBackend", FakeLlm)
        assert list(service.converse_stream("hi", 12)) == ["hi:12"]
        service.close()
        assert len(created) == 1
