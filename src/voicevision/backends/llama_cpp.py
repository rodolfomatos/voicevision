"""LLM inference via a supervised `llama-server` (ADR-001, ADR-002).

This is the only warm backend in v0.1. whisper.cpp and piper are one-shot
programs; llama-server is a daemon that keeps the model resident between calls,
which is where keeping a process alive actually matters — a 1.7B model takes
seconds to load.

## Reasoning traces

Qwen3 emits `thinking...` reasoning before its answer. Sending that to
text-to-speech produces the model thinking out loud, so `complete()` returns the
trace separately from the answer and `generate()` returns only the answer. The
filter in T014 works on the separation rather than trying to recover it from a
concatenated string.

Which JSON key carries the trace depends on the llama.cpp version and the
`--reasoning-format` flag, so several spellings are recognised. An unrecognised
shape is not an error — it degrades to "everything is content", which is the
pre-reasoning behaviour and is better than dropping the answer.

Implements LLMProvider protocol (M1).
"""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any, ClassVar, Final

from voicevision.backends.resident import ResidentBackend
from voicevision.core.protocols import Completion, LLMChunk, ProviderCapabilities, ProviderLifecycle
from voicevision.errors import (
    BackendExecutionError,
    ProviderTimeoutError,
)

#: Response keys llama.cpp has used for the reasoning trace.
_THINKING_KEYS: Final = ("thinking", "reasoning_content", "reasoning")

#: Refuse responses larger than this. A runaway server must not exhaust memory.
_MAX_RESPONSE_BYTES: Final = 32 * 1024 * 1024


@dataclass(frozen=True)
class LlamaCompletion:
    """A completion, with the reasoning trace kept separate from the answer."""

    content: str
    thinking: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def has_thinking(self) -> bool:
        return bool(self.thinking.strip())


class LlamaCppBackend(ResidentBackend):
    """Talk to a `llama-server` we start and supervise ourselves.

    Binds to loopback by default. The server has no authentication, so exposing
    it beyond localhost turns it into a network service (ADR-003 §4).

    Implements LLMProvider protocol.
    """

    executable: ClassVar[str] = "llama-server"

    install_hint: ClassVar[str] = (
        "Build llama.cpp: cmake -B build -DCMAKE_BUILD_TYPE=Release "
        "&& cmake --build build --target llama-server"
    )

    def __init__(
        self,
        model: str,
        *,
        host: str = "127.0.0.1",
        port: int = 8080,
        context_size: int = 2048,
        gpu_layers: int = 0,
        threads: int | None = None,
        request_timeout: float = 120.0,
        ready_timeout: float | None = None,
        extra_args: list[str] | None = None,
        binary: str | None = None,
    ) -> None:
        if not model:
            raise ValueError("model path is required — this backend does not download models")

        self._host = host
        self._port = port
        self._request_timeout = request_timeout
        self._model = model
        self._context_size = context_size
        self._gpu_layers = gpu_layers

        argv = [
            binary or self.executable,
            "-m",
            model,
            "--host",
            host,
            "--port",
            str(port),
            "-c",
            str(context_size),
            "-ngl",
            str(gpu_layers),
        ]
        if threads is not None:
            argv += ["-t", str(threads)]
        if extra_args:
            argv += list(extra_args)

        super().__init__(
            argv,
            ready_timeout=ready_timeout,
            name="llamacpp",
        )

    # -- introspection ----------------------------------------------------

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    @classmethod
    def available(cls) -> bool:
        return shutil.which(cls.executable) is not None

    # install_hint is a class attribute (line 69). The protocol expects a classmethod,
    # but @runtime_checkable only validates instance methods. Class attribute works.

    def describe(self) -> str:
        state = "running" if self.is_running else "stopped"
        return f"llamacpp [{state}] {self.base_url} model={self._model}"

    # -- readiness --------------------------------------------------------

    def _probe(self) -> bool:
        """Poll `/health`. Any exception means "not ready yet"."""
        request = urllib.request.Request(f"{self.base_url}/health", method="GET")
        with urllib.request.urlopen(request, timeout=2.0) as response:  # noqa: S310
            status: int = response.status
        return status == 200

    # -- inference --------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        stop: list[str] | None = None,
        token: CancellationToken | None = None,
        **_ignored: Any,
    ) -> str:
        """Return the answer text, with any reasoning trace discarded.

        This satisfies the LLMProvider Protocol. Call `complete()` when the trace
        matters — logging, or a filter that needs to know it was there.
        """
        if token is not None:
            token.throw_if_cancelled()
        completion = self.complete(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,
            token=token,
        )
        return completion.content

    def generate_stream(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        stop: list[str] | None = None,
        token: CancellationToken | None = None,
        **_ignored: Any,
    ) -> Generator[LLMChunk, None, None]:
        """Stream completion text chunks as they are generated.

        Uses llama.cpp's streaming mode (`stream=true`). Yields text chunks
        as they arrive from the server, allowing callers to start TTS
        synthesis before the full response is ready.
        """
        if token is not None:
            token.throw_if_cancelled()

        self.ensure_running()

        payload = self._build_stream_payload(prompt, temperature, max_tokens, stop)

        import urllib.request  # noqa: PLC0415 - lazy import

        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/completion",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self._request_timeout) as response:  # noqa: S310
                yield from self._process_stream_response(response, token)
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise BackendExecutionError(
                self.name,
                f"llama-server returned HTTP {exc.code}",
                command=self.command_line,
                returncode=exc.code,
                stderr=detail,
            ) from exc
        except urllib.error.URLError as exc:
            raise BackendExecutionError(
                self.name,
                f"could not reach llama-server at {self.base_url}: {exc.reason}. "
                "It may have exited or not finished loading the model.",
                command=self.command_line,
                stderr=self.server_log(),
            ) from exc

    def _build_stream_payload(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        stop: list[str] | None,
    ) -> dict[str, Any]:
        """Build the payload for streaming completion request."""
        payload: dict[str, Any] = {
            "prompt": prompt,
            "temperature": temperature,
            "n_predict": max_tokens,
            "stream": True,
        }
        if stop:
            payload["stop"] = stop
        return payload

    def _process_stream_response(
        self,
        response: object,  # urllib.response.addinfourl (avoid import at top level)
        token: CancellationToken | None,
    ) -> Generator[LLMChunk, None, None]:
        """Process the streaming response from llama-server."""
        for line in response:
            if token is not None:
                token.throw_if_cancelled()
            line = line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]  # Remove "data: " prefix
            if data_str.strip() == "[DONE]":
                yield LLMChunk(content="", is_final=True)
                break
            try:
                chunk = json.loads(data_str)
                content = chunk.get("content", "")
                thinking = self._extract_thinking(chunk)
                if content:
                    yield LLMChunk(content=content, thinking=thinking)
            except json.JSONDecodeError:
                continue  # Skip malformed JSON lines

    def _extract_thinking(self, chunk: dict[str, Any]) -> str:
        """Extract thinking from response chunk."""
        for key in _THINKING_KEYS:
            candidate = chunk.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        return ""

    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        stop: list[str] | None = None,
        token: CancellationToken | None = None,
        **_ignored: Any,
    ) -> Completion:
        """Run a completion and return content and reasoning separately."""
        if token is not None:
            token.throw_if_cancelled()

        self.ensure_running()

        payload: dict[str, Any] = {
            "prompt": prompt,
            "temperature": temperature,
            "n_predict": max_tokens,
            "stream": False,
        }
        if stop:
            payload["stop"] = stop

        body = self._post("/completion", payload)
        llama_completion = self.parse_completion(body)
        return Completion(
            content=llama_completion.content,
            thinking=llama_completion.thinking,
            raw=llama_completion.raw,
        )

    @staticmethod
    def parse_completion(body: dict[str, Any]) -> LlamaCompletion:
        """Split a llama.cpp response into answer and reasoning trace.

        The trace key varies by version and flags, so several spellings are
        accepted. An unrecognised shape keeps everything as content: an older
        server that knows nothing about reasoning then behaves exactly as it did
        before qwen3, which beats discarding the answer.
        """
        content = body.get("content")
        thinking = ""

        if not isinstance(content, str):
            # Some builds return per-token choices instead of a flat string.
            choices = body.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    content = first.get("content") or first.get("text") or ""
                else:
                    content = str(first)
            else:
                content = ""

        for key in _THINKING_KEYS:
            candidate = body.get(key)
            if isinstance(candidate, str) and candidate.strip():
                thinking = candidate
                break

        return LlamaCompletion(
            content=content.strip(),
            thinking=thinking.strip(),
            raw=body,
        )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON and decode the JSON response, or raise something legible."""
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._request_timeout) as response:  # noqa: S310
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise BackendExecutionError(
                self.name,
                f"llama-server returned HTTP {exc.code}",
                command=self.command_line,
                returncode=exc.code,
                stderr=detail,
            ) from exc
        except urllib.error.URLError as exc:
            raise BackendExecutionError(
                self.name,
                f"could not reach llama-server at {self.base_url}: {exc.reason}. "
                "It may have exited or not finished loading the model.",
                command=self.command_line,
                stderr=self.server_log(),
            ) from exc
        except TimeoutError as exc:
            raise ProviderTimeoutError(
                self.name,
                "llm",
                self._request_timeout,
                command=self.command_line,
            ) from exc

        if len(raw) > _MAX_RESPONSE_BYTES:
            raise BackendExecutionError(
                self.name,
                f"response exceeded {_MAX_RESPONSE_BYTES} bytes — refusing to buffer it",
                command=self.command_line,
            )

        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BackendExecutionError(
                self.name,
                f"llama-server returned non-JSON: {exc}",
                command=self.command_line,
                stderr=raw[:512].decode("utf-8", errors="replace"),
            ) from exc

        if not isinstance(decoded, dict):
            raise BackendExecutionError(
                self.name,
                f"expected a JSON object, got {type(decoded).__name__}",
                command=self.command_line,
            )
        return decoded

    # -- Provider protocol -------------------------------------------------

    @property
    def name(self) -> str:
        return "llamacpp"

    @property
    def modality(self) -> str:
        return "llm"

    def capabilities(self) -> ProviderCapabilities:
        from voicevision.core.protocols import ProviderCapabilities
        return ProviderCapabilities(
            streaming=True,
            languages=frozenset(),  # LLM is language-agnostic
            models=frozenset({"qwen3-1.7b", "qwen3-4b", "llama3-8b", "mistral-7b"}),
            max_concurrent=4,
            supports_cancellation=True,
        )

    def lifecycle(self) -> ProviderLifecycle:
        return self

    def initialize(self) -> None:
        self.ensure_running()

    def shutdown(self) -> None:
        self.close()

    def health_check(self) -> bool:
        return self.is_running and self._probe()


# Forward reference for type hints
class CancellationToken:
    """Forward reference."""
    def throw_if_cancelled(self) -> None: ...
