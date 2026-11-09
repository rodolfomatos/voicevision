"""Standard-library client for the local voicevision HTTP/WebSocket API.

The integrations in ``integrations/`` — Home Assistant, VS Code, Obsidian,
Notion — all need the same three calls. Rather than each re-implementing
base64, JSON and a WebSocket handshake, they share this client.

Design constraints:

1. **Standard library only.** The package's import cost is a non-functional
   requirement (see ``test_import_cost``), and an integration must not force a
   new dependency into a minimal install.
2. **Explicit failure.** Every network/HTTP/protocol failure becomes
   :class:`VoiceVisionClientError` with the server's own message when there is
   one, so a Home Assistant log says "VOICEVISION_STT_MODEL is not set" rather
   than "HTTPError 500".
3. **No hidden retries.** The client does not retry: the server is local, and a
   caller that wants retries can add them with the information this module
   preserves.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from typing import Any, Final, cast
from urllib.parse import urlsplit

from voicevision.errors import VoiceVisionError
from voicevision.websocket import (
    OPCODE_CLOSE,
    OPCODE_PING,
    OPCODE_TEXT,
    WebSocketClosed,
    WebSocketConnection,
    accept_key,
)

#: Where ``voicevision-server`` listens by default.
DEFAULT_BASE_URL: Final = "http://127.0.0.1:8765"
DEFAULT_TIMEOUT: Final = 120.0

#: A handshake response is a few hundred bytes; anything larger is a mistake.
_MAX_HANDSHAKE_BYTES: Final = 64 * 1024


class VoiceVisionClientError(VoiceVisionError):
    """The local voicevision server could not be reached or returned an error."""


def _encode_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _read_handshake(sock: socket.socket) -> bytes:
    """Read the HTTP response headers of the WebSocket upgrade."""
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise VoiceVisionClientError("server closed during WebSocket handshake")
        data.extend(chunk)
        if len(data) > _MAX_HANDSHAKE_BYTES:
            raise VoiceVisionClientError("WebSocket handshake response too large")
    return bytes(data)


class VoiceVisionClient:
    """Synchronous client for one voicevision server."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: str = "",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    # -- HTTP -------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Return ``{"status": "ok", "version": ...}``."""
        return self._request("GET", "/health")

    def transcribe(self, audio: bytes, language: str | None = None) -> dict[str, Any]:
        """Transcribe WAV or raw 16 kHz mono PCM16 audio."""
        payload: dict[str, Any] = {"audio_base64": _encode_b64(audio)}
        if language:
            payload["language"] = language
        return self._request("POST", "/transcribe", payload)

    def describe(self, image: bytes, question: str | None = None) -> dict[str, Any]:
        """Describe an image, or answer *question* about it."""
        payload: dict[str, Any] = {"image_base64": _encode_b64(image)}
        if question:
            payload["question"] = question
        return self._request("POST", "/describe", payload)

    def converse(self, text: str, max_tokens: int | None = None) -> dict[str, Any]:
        """Ask the LLM a question and return the whole answer."""
        payload: dict[str, Any] = {"text": text}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return self._request("POST", "/converse", payload)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(  # nosec B310 - local, operator-configured URL
                request,
                timeout=self.timeout,
            ) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            raise VoiceVisionClientError(self._http_error_message(exc)) from exc
        except urllib.error.URLError as exc:
            raise VoiceVisionClientError(
                f"cannot reach {self.base_url}: {exc.reason}"
            ) from exc
        except OSError as exc:
            raise VoiceVisionClientError(f"cannot reach {self.base_url}: {exc}") from exc

        try:
            decoded = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise VoiceVisionClientError("server returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise VoiceVisionClientError("server returned a non-object JSON body")
        return cast(dict[str, Any], decoded)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @staticmethod
    def _http_error_message(exc: urllib.error.HTTPError) -> str:
        try:
            payload = json.loads(exc.read())
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return f"HTTP {exc.code}: {exc.reason}"
        if isinstance(payload, dict):
            message = payload.get("error")
            if isinstance(message, str):
                return f"HTTP {exc.code}: {message}"
        return f"HTTP {exc.code}: {exc.reason}"

    # -- WebSocket --------------------------------------------------------

    def stream(
        self,
        chunks: Iterable[bytes],
        language: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream audio to ``/stream`` and yield the server's JSON messages.

        The iterator ends on ``done``, on ``error``, or when the server closes
        the connection. The socket is closed in every case.
        """
        sock, ws = self._connect_stream()
        try:
            for chunk in chunks:
                message: dict[str, Any] = {
                    "type": "audio",
                    "audio_base64": _encode_b64(chunk),
                }
                if language:
                    message["language"] = language
                ws.send_json(message)
            ws.send_json({"type": "end"})
            yield from self._read_stream(ws)
        finally:
            ws.close()
            sock.close()

    @staticmethod
    def _read_stream(ws: WebSocketConnection) -> Iterator[dict[str, Any]]:
        while True:
            try:
                frame = ws.recv()
            except WebSocketClosed:
                return
            if frame.opcode == OPCODE_CLOSE:
                return
            if frame.opcode == OPCODE_PING:
                ws.pong(frame.payload)
                continue
            if frame.opcode != OPCODE_TEXT:
                raise VoiceVisionClientError(f"unexpected WebSocket opcode {frame.opcode}")
            try:
                message = json.loads(frame.payload)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise VoiceVisionClientError("server sent invalid JSON") from exc
            if not isinstance(message, dict):
                raise VoiceVisionClientError("server sent a non-object JSON message")
            decoded = cast(dict[str, Any], message)
            yield decoded
            if decoded.get("type") in {"done", "error"}:
                return

    def _connect_stream(self) -> tuple[socket.socket, WebSocketConnection]:
        parts = urlsplit(self.base_url)
        host = parts.hostname or "127.0.0.1"
        port = parts.port or (443 if parts.scheme == "https" else 80)
        path = f"{parts.path.rstrip('/')}/stream"
        key = base64.b64encode(os.urandom(16)).decode("ascii")

        lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}:{port}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
        ]
        if self.token:
            lines.append(f"Authorization: Bearer {self.token}")
        request = ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")

        try:
            sock = socket.create_connection((host, port), timeout=self.timeout)
        except OSError as exc:
            raise VoiceVisionClientError(f"cannot reach {self.base_url}: {exc}") from exc

        try:
            sock.sendall(request)
            response = _read_handshake(sock)
            status_line = response.split(b"\r\n", 1)[0]
            try:
                status = int(status_line.split(b" ", 2)[1])
            except (IndexError, ValueError) as exc:
                raise VoiceVisionClientError(
                    f"invalid WebSocket handshake response: {status_line!r}"
                ) from exc
            if status != 101:
                raise VoiceVisionClientError(f"WebSocket upgrade failed: HTTP {status}")
            if accept_key(key).encode("ascii") not in response:
                raise VoiceVisionClientError(
                    "server returned an invalid Sec-WebSocket-Accept header"
                )
            ws = WebSocketConnection(
                sock.makefile("rb"),
                sock.makefile("wb"),
                mask_outgoing=True,
                require_mask=False,
            )
            return sock, ws
        except Exception:
            sock.close()
            raise
