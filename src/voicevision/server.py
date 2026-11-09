"""Local HTTP server exposing voicevision over JSON.

Why this exists: editor plugins, Home Assistant and any other process need a
stable interface that is not "import this Python package and know its
internals". The server exposes three capabilities — transcribe audio, describe
an image, answer text — as synchronous JSON endpoints.

Design constraints, in order:

1. **Standard library only.** ``http.server`` + ``json`` + ``base64``. The
   server must not add a mandatory dependency to a package whose import cost
   is a deliberate non-functional requirement (see ``test_import_cost``).
2. **Localhost by default.** Binding to ``127.0.0.1`` is not a detail: the
   server has no user model and anyone who reaches it can spend CPU and read
   transcripts. ``--host`` is the explicit opt-in to expose it.
3. **Optional bearer auth.** ``VOICEVISION_SERVER_TOKEN`` turns on a
   constant-time ``Authorization: Bearer`` check. Unset means "no auth",
   which is only safe because of constraint 2.

The endpoints reuse the same backend classes as the CLI, so behaviour and
configuration stay identical. Heavy backends are created lazily on first use:
a request for ``/health`` must not spawn whisper or llama.cpp.
"""

from __future__ import annotations

import argparse
import base64
import hmac
import json
import os
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Final, cast
from urllib.parse import urlsplit

from voicevision import __version__
from voicevision.audio import pcm16_to_wav, require_whisper_format
from voicevision.backends.llama_cpp import LlamaCppBackend
from voicevision.backends.vision import MoondreamBackend
from voicevision.backends.whisper_cpp import WhisperCppBackend
from voicevision.errors import ConfigurationError, VoiceVisionError
from voicevision.websocket import (
    CLOSE_INVALID_DATA,
    CLOSE_UNSUPPORTED,
    OPCODE_CLOSE,
    OPCODE_PING,
    OPCODE_PONG,
    OPCODE_TEXT,
    WebSocketClosed,
    WebSocketConnection,
    WebSocketProtocolError,
    accept_key,
)

#: Loopback only unless the operator says otherwise.
DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8765

#: Hard cap on request bodies. Base64 inflates payloads by ~33%, so 10 MiB
#: covers roughly 7.5 MiB of audio or image — far more than a single request
#: needs, and small enough that a hostile client cannot exhaust memory.
MAX_BODY_BYTES: Final = 10 * 1024 * 1024

#: Upper bound for a caller-supplied ``max_tokens``. The model's own limit is
#: lower; this only stops a request from asking for an absurd generation.
MAX_TOKENS_LIMIT: Final = 8192

#: Paths that exist, mapped to the methods they accept.
_ROUTES: Final = {
    "/health": "GET",
    "/stream": "GET",
    "/transcribe": "POST",
    "/describe": "POST",
    "/converse": "POST",
}


def _env_int(name: str, default: int) -> int:
    """Parse an integer env var, falling back to *default* on anything invalid."""
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    """Parse a boolean env var (0/false/no/off disable; anything else enables)."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


@dataclass
class ServerConfig:
    """Everything the server needs, read from the environment.

    Model paths are deliberately *not* validated at construction: a server
    that only answers ``/health`` should start even when whisper is not
    installed. The failure is reported per request, with the install hint.
    """

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    token: str = ""
    quiet: bool = False
    max_body_bytes: int = MAX_BODY_BYTES

    stt_model: str = ""
    stt_language: str = "en"

    llm_model: str = ""
    llm_host: str = "127.0.0.1"
    llm_port: int = 8080
    llm_max_tokens: int = 512

    vision_model: str = ""
    vision_host: str = "127.0.0.1"
    vision_port: int = 8081


def load_config() -> ServerConfig:
    """Build a :class:`ServerConfig` from environment variables.

    Server-specific variables are ``VOICEVISION_SERVER_HOST``,
    ``VOICEVISION_SERVER_PORT`` and ``VOICEVISION_SERVER_TOKEN``. Backend
    variables are the same ones the rest of the package uses, so one
    ``~/.profile`` configures both the CLI and the server.
    """
    return ServerConfig(
        host=os.environ.get("VOICEVISION_SERVER_HOST", DEFAULT_HOST),
        port=_env_int("VOICEVISION_SERVER_PORT", DEFAULT_PORT),
        token=os.environ.get("VOICEVISION_SERVER_TOKEN", ""),
        quiet=_env_bool("VOICEVISION_QUIET", False),
        stt_model=os.environ.get("VOICEVISION_STT_MODEL", ""),
        stt_language=os.environ.get("VOICEVISION_STT_LANGUAGE", "en"),
        llm_model=os.environ.get("VOICEVISION_LLM_MODEL", ""),
        llm_host=os.environ.get("VOICEVISION_LLM_HOST", "127.0.0.1"),
        llm_port=_env_int("VOICEVISION_LLM_PORT", 8080),
        llm_max_tokens=_env_int("VOICEVISION_LLM_MAX_TOKENS", 512),
        vision_model=os.environ.get("VOICEVISION_VISION_MODEL", ""),
        vision_host=os.environ.get("VOICEVISION_VISION_HOST", "127.0.0.1"),
        vision_port=_env_int("VOICEVISION_VISION_PORT", 8081),
    )


class _BadRequest(Exception):
    """A client error carrying the HTTP status to send back."""

    def __init__(self, status: HTTPStatus, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(message)


def _normalise_audio(data: bytes) -> bytes:
    """Return WAV bytes, accepting either a WAV file or raw PCM16.

    whisper.cpp only accepts 16 kHz mono PCM16 WAV. Raw PCM16 is wrapped here;
    a WAV payload is validated rather than silently resampled (see
    ``voicevision.audio`` for why resampling is never automatic).
    """
    if not data:
        raise _BadRequest(HTTPStatus.BAD_REQUEST, "audio payload is empty")
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        try:
            require_whisper_format(data)
        except ValueError as exc:
            raise _BadRequest(HTTPStatus.BAD_REQUEST, str(exc)) from exc
        return data
    if len(data) % 2 != 0:
        raise _BadRequest(
            HTTPStatus.BAD_REQUEST,
            "raw PCM16 payload has an odd number of bytes",
        )
    return pcm16_to_wav(data)


def _decode_base64(payload: dict[str, Any], field: str) -> bytes:
    """Decode a required base64 string field, or raise 400."""
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise _BadRequest(HTTPStatus.BAD_REQUEST, f"missing or invalid {field!r}")
    try:
        # binascii.Error is a ValueError subclass; one handler is enough.
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise _BadRequest(HTTPStatus.BAD_REQUEST, f"{field!r} is not valid base64") from exc


def _required_text(payload: dict[str, Any], field: str) -> str:
    """Return a required non-empty string field, or raise 400."""
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise _BadRequest(HTTPStatus.BAD_REQUEST, f"{field!r} must be a non-empty string")
    return value


class VoiceVisionService:
    """Owns the lazily-created backends and implements the capabilities.

    Kept separate from the HTTP handler so tests can substitute a fake service
    and so the endpoints stay a thin translation layer.
    """

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        # One whisper backend per language: the language is baked into argv,
        # and switching it per request would spawn a process each time.
        self._stt: dict[str, WhisperCppBackend] = {}
        self._llm: LlamaCppBackend | None = None
        self._vision: MoondreamBackend | None = None

    def transcribe(self, wav: bytes, language: str) -> tuple[str, float]:
        """Transcribe WAV audio; return the transcript and elapsed ms."""
        # Handle auto language detection
        if language == "auto":
            if not self.config.stt_model:
                raise ConfigurationError(
                    "VOICEVISION_STT_MODEL is not set — cannot transcribe audio"
                )
            # Create a temporary backend for language detection
            stt_detect = WhisperCppBackend(model=self.config.stt_model, language="en")
            detected_lang = stt_detect.detect_language(wav)
            # Now transcribe with the detected language
            stt_auto = WhisperCppBackend(model=self.config.stt_model, language=detected_lang)
            started = time.monotonic()
            transcript = stt_auto.transcribe(wav)
            elapsed_ms = (time.monotonic() - started) * 1000.0
            return transcript, elapsed_ms

        stt: WhisperCppBackend | None = self._stt.get(language)
        if stt is None:
            if not self.config.stt_model:
                raise ConfigurationError(
                    "VOICEVISION_STT_MODEL is not set — cannot transcribe audio"
                )
            stt = WhisperCppBackend(model=self.config.stt_model, language=language)
            self._stt[language] = stt
        started = time.monotonic()
        transcript = stt.transcribe(wav)
        elapsed_ms = (time.monotonic() - started) * 1000.0
        return transcript, elapsed_ms

    def describe(self, image: bytes, question: str) -> str:
        """Describe an image (or answer a question about it)."""
        if not self.config.vision_model:
            raise ConfigurationError(
                "VOICEVISION_VISION_MODEL is not set — cannot describe images"
            )
        if self._vision is None:
            self._vision = MoondreamBackend(
                model=self.config.vision_model,
                host=self.config.vision_host,
                port=self.config.vision_port,
            )
        return self._vision.describe(image, prompt=question)

    def converse(self, text: str, max_tokens: int) -> str:
        """Return the LLM's answer to *text*, without the reasoning trace."""
        if not self.config.llm_model:
            raise ConfigurationError("VOICEVISION_LLM_MODEL is not set — cannot answer text")
        if self._llm is None:
            self._llm = LlamaCppBackend(
                model=self.config.llm_model,
                host=self.config.llm_host,
                port=self.config.llm_port,
            )
        completion = self._llm.complete(text, max_tokens=max_tokens)
        return completion.content

    def converse_stream(self, text: str, max_tokens: int) -> Iterator[str]:
        """Yield the LLM's answer in chunks, without the reasoning trace."""
        if not self.config.llm_model:
            raise ConfigurationError("VOICEVISION_LLM_MODEL is not set — cannot answer text")
        if self._llm is None:
            self._llm = LlamaCppBackend(
                model=self.config.llm_model,
                host=self.config.llm_host,
                port=self.config.llm_port,
            )
        yield from self._llm.complete_stream(text, max_tokens=max_tokens)

    def close(self) -> None:
        """Release every backend that holds resources.

        whisper.cpp and llama.cpp are subprocess-backed and must be shut down.
        ``MoondreamBackend`` opens an ``httpx`` client per call and owns no
        process, so there is nothing to release.
        """
        for backend in [*self._stt.values(), self._llm]:
            if backend is not None:
                backend.close()


class VoiceVisionHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server carrying the service and its configuration.

    Threading matters because a whisper or llama.cpp call blocks for seconds;
    a single-threaded server would make ``/health`` unresponsive while a
    transcription runs.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        config: ServerConfig,
        service: VoiceVisionService | None = None,
    ) -> None:
        self.config = config
        self.app = service if service is not None else VoiceVisionService(config)
        super().__init__((config.host, config.port), _RequestHandler)


class _RequestHandler(BaseHTTPRequestHandler):
    """Translate HTTP requests into :class:`VoiceVisionService` calls."""

    server_version = f"voicevision/{__version__}"

    @property
    def _app(self) -> VoiceVisionService:
        return cast(VoiceVisionHTTPServer, self.server).app

    @property
    def _config(self) -> ServerConfig:
        return cast(VoiceVisionHTTPServer, self.server).config

    # -- routing ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - name required by BaseHTTPRequestHandler
        path = urlsplit(self.path).path
        if path == "/stream":
            self._handle_stream()
            return
        if path != "/health":
            self._reject_route(path, "GET")
            return
        if not self._check_auth():
            return
        self._send_json(
            HTTPStatus.OK,
            {"status": "ok", "version": __version__},
        )

    def do_POST(self) -> None:  # noqa: N802 - name required by BaseHTTPRequestHandler
        path = urlsplit(self.path).path
        if path not in ("/transcribe", "/describe", "/converse"):
            self._reject_route(path, "POST")
            return
        if not self._check_auth():
            return
        try:
            payload = self._read_json()
            if path == "/transcribe":
                result = self._handle_transcribe(payload)
            elif path == "/describe":
                result = self._handle_describe(payload)
            else:
                result = self._handle_converse(payload)
        except _BadRequest as exc:
            self._send_error(exc.status, exc.message)
            return
        except ConfigurationError as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        except VoiceVisionError as exc:
            self._send_error(HTTPStatus.BAD_GATEWAY, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - never leak a traceback to a client
            self._send_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"internal error: {exc}",
            )
            return
        self._send_json(HTTPStatus.OK, result)

    def _reject_route(self, path: str, method: str) -> None:
        """Send 405 for a known path used with the wrong method, else 404."""
        allowed = _ROUTES.get(path)
        if allowed is None:
            self._send_error(HTTPStatus.NOT_FOUND, f"unknown path: {path}")
            return
        self._send_error(
            HTTPStatus.METHOD_NOT_ALLOWED,
            f"method {method} not allowed on {path}",
            headers={"Allow": allowed},
        )

    # -- endpoint handlers ------------------------------------------------

    def _handle_transcribe(self, payload: dict[str, Any]) -> dict[str, Any]:
        wav = _normalise_audio(_decode_base64(payload, "audio_base64"))
        language = payload.get("language", self._config.stt_language)
        if not isinstance(language, str) or not language.strip():
            raise _BadRequest(
                HTTPStatus.BAD_REQUEST,
                "'language' must be a non-empty string",
            )
        transcript, elapsed_ms = self._app.transcribe(wav, language)
        return {
            "transcript": transcript,
            "language": language if language != "auto" else "auto",
            "detected_language": language if language == "auto" else None,
            "transcription_ms": round(elapsed_ms, 3),
        }

    def _handle_describe(self, payload: dict[str, Any]) -> dict[str, Any]:
        image = _decode_base64(payload, "image_base64")
        question = payload.get("question", "Describe this image in detail.")
        if not isinstance(question, str) or not question.strip():
            raise _BadRequest(
                HTTPStatus.BAD_REQUEST,
                "'question' must be a non-empty string",
            )
        description = self._app.describe(image, question)
        return {"description": description}

    def _handle_converse(self, payload: dict[str, Any]) -> dict[str, Any]:
        text = _required_text(payload, "text")
        max_tokens = payload.get("max_tokens", self._config.llm_max_tokens)
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
            raise _BadRequest(
                HTTPStatus.BAD_REQUEST,
                "'max_tokens' must be an integer",
            )
        if not 1 <= max_tokens <= MAX_TOKENS_LIMIT:
            raise _BadRequest(
                HTTPStatus.BAD_REQUEST,
                f"'max_tokens' must be between 1 and {MAX_TOKENS_LIMIT}",
            )
        response = self._app.converse(text, max_tokens)
        return {"response": response}

    # -- WebSocket streaming ----------------------------------------------

    def _handle_stream(self) -> None:
        """Validate the upgrade, then hand the socket to the streaming loop."""
        if not self._check_auth():
            return

        upgrade = self.headers.get("Upgrade", "").lower()
        connection = self.headers.get("Connection", "").lower()
        if "websocket" not in upgrade or "upgrade" not in connection:
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "expected a WebSocket upgrade",
            )
            return

        if self.headers.get("Sec-WebSocket-Version", "") != "13":
            self._send_error(
                HTTPStatus.UPGRADE_REQUIRED,
                "unsupported WebSocket version",
                headers={"Sec-WebSocket-Version": "13"},
            )
            return

        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self._send_error(
                HTTPStatus.BAD_REQUEST,
                "missing Sec-WebSocket-Key",
            )
            return

        self.send_response(HTTPStatus.SWITCHING_PROTOCOLS)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept_key(key))
        self.end_headers()
        self.close_connection = True

        self._stream_loop(WebSocketConnection(self.rfile, self.wfile))

    def _stream_loop(self, ws: WebSocketConnection) -> None:
        """Consume JSON frames until the peer closes or violates the protocol."""
        audio = bytearray()
        language = self._config.stt_language
        try:
            while True:
                frame = ws.recv()
                if frame.opcode == OPCODE_CLOSE:
                    ws.close()
                    return
                if frame.opcode == OPCODE_PING:
                    ws.pong(frame.payload)
                    continue
                if frame.opcode == OPCODE_PONG:
                    continue
                if frame.opcode != OPCODE_TEXT:
                    ws.close(CLOSE_UNSUPPORTED, "only text frames are supported")
                    return

                keep_open, language = self._handle_stream_text(
                    ws,
                    frame.payload,
                    audio,
                    language,
                )
                if not keep_open:
                    return
        except WebSocketClosed:
            return
        except WebSocketProtocolError as exc:
            ws.close(exc.code, exc.reason)
        except OSError:
            return

    def _handle_stream_text(
        self,
        ws: WebSocketConnection,
        payload: bytes,
        audio: bytearray,
        language: str,
    ) -> tuple[bool, str]:
        """Handle one text frame. Returns (keep_open, current_language)."""
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            ws.close(CLOSE_INVALID_DATA, "invalid UTF-8")
            return False, language

        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            self._ws_error(ws, "malformed JSON")
            return True, language
        if not isinstance(message, dict):
            self._ws_error(ws, "message must be a JSON object")
            return True, language

        message_type = message.get("type")
        if message_type == "audio":
            requested = self._handle_stream_audio(ws, message, audio)
            return True, requested if requested is not None else language
        if message_type == "reset":
            audio.clear()
            return True, language
        if message_type == "end":
            self._ws_finish(ws, bytes(audio), language)
            audio.clear()
            return True, language

        self._ws_error(ws, f"unknown message type: {message_type!r}")
        return True, language

    def _handle_stream_audio(
        self,
        ws: WebSocketConnection,
        message: dict[str, Any],
        audio: bytearray,
    ) -> str | None:
        """Append one audio chunk; return a language override if present."""
        try:
            chunk = _decode_base64(message, "audio_base64")
        except _BadRequest as exc:
            self._ws_error(ws, exc.message)
            return None
        if len(audio) + len(chunk) > self._config.max_body_bytes:
            audio.clear()
            self._ws_error(
                ws,
                f"buffered audio exceeds {self._config.max_body_bytes} bytes",
            )
            return None
        audio.extend(chunk)
        requested_language = message.get("language")
        if isinstance(requested_language, str) and requested_language.strip():
            return requested_language
        return None

    def _ws_finish(
        self,
        ws: WebSocketConnection,
        audio: bytes,
        language: str,
    ) -> None:
        """Transcribe buffered audio, then stream the LLM answer as tokens."""
        if not audio:
            self._ws_error(ws, "no audio received")
            return
        try:
            wav = _normalise_audio(audio)
            transcript, elapsed_ms = self._app.transcribe(wav, language)
            ws.send_json(
                {
                    "type": "transcript",
                    "transcript": transcript,
                    "language": language,
                    "transcription_ms": round(elapsed_ms, 3),
                }
            )
            for chunk in self._app.converse_stream(transcript, self._config.llm_max_tokens):
                if chunk:
                    ws.send_json({"type": "token", "text": chunk})
            ws.send_json({"type": "done"})
        except _BadRequest as exc:
            self._ws_error(ws, exc.message)
        except ConfigurationError as exc:
            self._ws_error(ws, str(exc))
        except VoiceVisionError as exc:
            self._ws_error(ws, str(exc))
        except Exception as exc:  # noqa: BLE001 - report, do not kill the socket
            self._ws_error(ws, f"internal error: {exc}")

    @staticmethod
    def _ws_error(ws: WebSocketConnection, message: str) -> None:
        ws.send_json({"type": "error", "error": message})

    # -- request plumbing -------------------------------------------------

    def _check_auth(self) -> bool:
        """Enforce bearer auth when configured; return False after a 401."""
        token = self._config.token
        if not token:
            return True
        header = self.headers.get("Authorization", "")
        if hmac.compare_digest(header, f"Bearer {token}"):
            return True
        self._send_error(
            HTTPStatus.UNAUTHORIZED,
            "unauthorized",
            headers={"WWW-Authenticate": 'Bearer realm="voicevision"'},
        )
        return False

    def _read_json(self) -> dict[str, Any]:
        """Read and parse a JSON object body, enforcing the size cap."""
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise _BadRequest(
                HTTPStatus.LENGTH_REQUIRED,
                "Content-Length is required",
            )
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise _BadRequest(
                HTTPStatus.BAD_REQUEST,
                "invalid Content-Length",
            ) from exc
        if length < 0:
            raise _BadRequest(HTTPStatus.BAD_REQUEST, "invalid Content-Length")
        if length > self._config.max_body_bytes:
            # Do not read the body: draining a hostile payload is the attack.
            self.close_connection = True
            raise _BadRequest(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                f"request body exceeds {self._config.max_body_bytes} bytes",
            )
        body = self.rfile.read(length)
        if len(body) != length:
            raise _BadRequest(
                HTTPStatus.BAD_REQUEST,
                "incomplete request body",
            )
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _BadRequest(
                HTTPStatus.BAD_REQUEST,
                f"malformed JSON: {exc}",
            ) from exc
        if not isinstance(payload, dict):
            raise _BadRequest(
                HTTPStatus.BAD_REQUEST,
                "request body must be a JSON object",
            )
        return payload

    # -- responses --------------------------------------------------------

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(
        self,
        status: HTTPStatus,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Silence per-request logging in quiet mode."""
        if not self._config.quiet:
            super().log_message(format, *args)


def create_server(
    config: ServerConfig,
    service: VoiceVisionService | None = None,
) -> VoiceVisionHTTPServer:
    """Create (and bind) a server. Binding happens here, not in ``serve``.

    Raises:
        OSError: if the address is already in use or not bindable.
    """
    return VoiceVisionHTTPServer(config, service=service)


def serve(config: ServerConfig | None = None) -> int:
    """Run the server until interrupted; return a process exit code."""
    config = config if config is not None else load_config()
    try:
        server = create_server(config)
    except OSError as exc:
        print(f"error: could not bind {config.host}:{config.port}: {exc}", file=sys.stderr)
        return 2

    actual_port = int(server.server_address[1])
    if not config.quiet:
        print(
            f"voicevision-server listening on http://{config.host}:{actual_port}",
            file=sys.stderr,
        )
        if config.host not in {"127.0.0.1", "::1", "localhost"}:
            print(
                "warning: server is reachable beyond localhost"
                + (" (bearer auth enabled)" if config.token else " without auth"),
                file=sys.stderr,
            )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.app.close()
    return 0


def main() -> None:
    """CLI entry point for ``voicevision-server``."""
    parser = argparse.ArgumentParser(
        description="voicevision local HTTP server: /health, /transcribe, /describe, /converse",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Bind address (default: 127.0.0.1). Use 0.0.0.0 to expose the "
        "server on the network — only with --token set.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Bind port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Require 'Authorization: Bearer <token>' (overrides "
        "VOICEVISION_SERVER_TOKEN)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress the startup banner and per-request logging",
    )
    args = parser.parse_args()

    config = load_config()
    if args.host is not None:
        config = replace(config, host=args.host)
    if args.port is not None:
        config = replace(config, port=args.port)
    if args.token is not None:
        config = replace(config, token=args.token)
    if args.quiet:
        config = replace(config, quiet=True)

    sys.exit(serve(config))


if __name__ == "__main__":
    main()
