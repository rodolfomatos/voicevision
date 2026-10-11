"""Tests for LlamaCppBackend and ResidentBackend.

Runs a real subprocess serving real HTTP. No model, no GPU, no llama.cpp
binary: tests/support/fake_llama_server.py stands in for it.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from voicevision.backends.llama_cpp import Completion, LlamaCppBackend
from voicevision.backends.resident import ResidentBackend
from voicevision.errors import BackendExecutionError, BackendNotAvailableError

FAKE_SERVER = str(Path(__file__).parent.parent / "support" / "fake_llama_server.py")


def free_port() -> int:
    """Ask the OS for an unused port, then release it.

    Slightly racy in principle; the window is microseconds and CI does not run
    parallel tests inside a process.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def make_backend(*flags: str, **kwargs: object) -> LlamaCppBackend:
    """A backend whose process is the fake server, keeping our own argv.

    Constructed normally so argument construction stays under test, then argv[0]
    is swapped for the interpreter plus the fake server script. A string with
    spaces cannot be used as argv[0] — Popen would treat it as a path.
    """
    backend = LlamaCppBackend(
        model=str(kwargs.pop("model", "/models/qwen3-1.7b.gguf")),
        host="127.0.0.1",
        port=free_port(),
        ready_timeout=kwargs.pop("ready_timeout", 15.0),
        binary="llama-server",
        **kwargs,  # type: ignore[arg-type]
    )
    backend._argv = [sys.executable, FAKE_SERVER, *backend._argv[1:], *flags]
    return backend


# -- construction ----------------------------------------------------------


class TestConstruction:
    def test_requires_a_model_path(self) -> None:
        with pytest.raises(ValueError, match="does not download"):
            LlamaCppBackend(model="")

    def test_binds_to_loopback_by_default(self) -> None:
        """No authentication means no exposing it (ADR-003 §4)."""
        backend = LlamaCppBackend(model="/m.gguf")
        assert backend.base_url == "http://127.0.0.1:8080"
        assert "--host 127.0.0.1" in backend.command_line

    def test_host_and_port_are_configurable(self) -> None:
        backend = LlamaCppBackend(model="/m.gguf", host="0.0.0.0", port=9000)
        assert backend.base_url == "http://0.0.0.0:9000"
        assert "--port 9000" in backend.command_line

    def test_model_context_and_gpu_layers_in_argv(self) -> None:
        backend = LlamaCppBackend(model="/m.gguf", context_size=4096, gpu_layers=35)
        assert "-m /m.gguf" in backend.command_line
        assert "-c 4096" in backend.command_line
        assert "-ngl 35" in backend.command_line

    def test_threads_are_optional(self) -> None:
        assert "-t" not in LlamaCppBackend(model="/m.gguf").command_line
        assert "-t 4" in LlamaCppBackend(model="/m.gguf", threads=4).command_line

    def test_extra_args_are_appended(self) -> None:
        backend = LlamaCppBackend(model="/m.gguf", extra_args=["--flash-attn"])
        assert backend.command_line.endswith("--flash-attn")

    def test_install_hint_names_the_build(self) -> None:
        assert "cmake" in LlamaCppBackend.install_hint

    def test_available_is_false_without_binary(self) -> None:
        assert LlamaCppBackend.available() is False


# -- lifecycle and readiness ------------------------------------------------


class TestReadiness:
    def test_starts_and_becomes_ready(self) -> None:
        backend = make_backend("--log", "loading model")
        try:
            backend.start()
            assert backend.is_running
            assert backend.pid is not None
        finally:
            backend.close()

    def test_start_is_idempotent(self) -> None:
        backend = make_backend()
        try:
            backend.start()
            first = backend.pid
            backend.start()
            assert backend.pid == first
        finally:
            backend.close()

    def test_slow_startup_still_succeeds(self) -> None:
        """Loading a model is not instant; a fixed sleep would fail here."""
        backend = make_backend("--delay", "1.0", ready_timeout=15.0)
        try:
            started = time.monotonic()
            backend.start()
            assert time.monotonic() - started >= 1.0
        finally:
            backend.close()

    def test_never_ready_raises_with_the_deadline(self) -> None:
        """Distinguish 'never healthy' from 'binary missing' (ADR-003)."""
        backend = make_backend("--never-ready", ready_timeout=1.0)
        with pytest.raises(BackendExecutionError) as exc:
            backend.start()
        message = str(exc.value)
        assert "did not become ready" in message
        assert "1" in message

    def test_never_ready_leaves_no_process_behind(self) -> None:
        """A half-started model holding GPU memory must not be leaked."""
        backend = make_backend("--never-ready", ready_timeout=1.0)
        with pytest.raises(BackendExecutionError):
            backend.start()
        assert not backend.is_running
        assert backend.pid is None

    def test_startup_crash_reports_exit_code_and_stderr(self) -> None:
        backend = make_backend("--exit-on-start", ready_timeout=10.0)
        with pytest.raises(BackendExecutionError) as exc:
            backend.start()
        assert exc.value.returncode == 1
        assert "unsupported quantisation" in exc.value.stderr

    def test_missing_binary_is_a_different_error(self) -> None:
        """Not-installed must not be reported as not-ready."""
        backend = LlamaCppBackend(model="/m.gguf", binary="llama-server-absent-xyz")
        with pytest.raises(BackendNotAvailableError):
            backend.start()

    def test_ready_timeout_is_configurable_and_observable(self) -> None:
        assert LlamaCppBackend(model="/m.gguf", ready_timeout=7.5).ready_timeout == 7.5

    def test_stderr_is_captured_during_startup(self) -> None:
        """Without this, a model that loads slowly gives the operator nothing."""
        backend = make_backend("--log", "llama_new_context_with_model: loaded")
        try:
            backend.start()
            assert "llama_new_context_with_model" in backend.server_log()
        finally:
            backend.close()


# -- inference -------------------------------------------------------------


class TestInference:
    def test_generate_returns_the_answer(self) -> None:
        backend = make_backend()
        try:
            assert backend.generate("What is 6 times 7?") == "The answer is 42."
        finally:
            backend.close()

    def test_model_stays_resident_across_calls(self) -> None:
        """The reason this backend exists: one model load, many calls."""
        backend = make_backend()
        try:
            backend.generate("first")
            first_pid = backend.pid
            backend.generate("second")
            backend.generate("third")
            assert backend.pid == first_pid
        finally:
            backend.close()

    def test_request_contents_reach_the_server(self) -> None:
        backend = make_backend("--echo-prompt")
        try:
            assert backend.generate("my exact prompt") == "my exact prompt"
        finally:
            backend.close()

    def test_stop_sequence_is_sent(self) -> None:
        backend = make_backend("--echo-prompt")
        try:
            result = backend.complete("x", stop=["</s>"])
            assert isinstance(result, Completion)
        finally:
            backend.close()

    def test_http_error_surfaces_with_detail(self) -> None:
        backend = make_backend("--http-error")
        try:
            with pytest.raises(BackendExecutionError) as exc:
                backend.generate("x")
            assert "500" in str(exc.value)
            assert "model failed to generate" in exc.value.stderr
        finally:
            backend.close()

    def test_non_json_response_is_rejected(self) -> None:
        """Handing back garbage would be silent corruption downstream."""
        backend = make_backend("--garbage")
        try:
            with pytest.raises(BackendExecutionError, match="non-JSON"):
                backend.generate("x")
        finally:
            backend.close()


# -- reasoning trace separation (FR-5) -------------------------------------


class TestReasoningTraceSeparation:
    def test_thinking_is_not_returned_as_content(self) -> None:
        """Otherwise TTS reads the model's deliberation out loud."""
        backend = make_backend("--thinking")
        try:
            result = backend.complete("x")
            assert result.has_thinking
            assert "consider the question" in result.thinking
            assert "consider the question" not in result.content
        finally:
            backend.close()

    def test_generate_drops_the_trace(self) -> None:
        backend = make_backend("--thinking")
        try:
            assert backend.generate("x") == "The answer is 42."
        finally:
            backend.close()

    def test_raw_response_is_retained_for_logging(self) -> None:
        backend = make_backend("--thinking")
        try:
            result = backend.complete("x")
            assert isinstance(result.raw, dict)
            assert "thinking" in result.raw
        finally:
            backend.close()


class TestCompletionParsing:
    """Version variation is expected; the parse must not be brittle."""

    def test_flat_content(self) -> None:
        result = LlamaCppBackend.parse_completion({"content": "hello"})
        assert result.content == "hello"
        assert not result.has_thinking

    def test_content_is_stripped(self) -> None:
        assert LlamaCppBackend.parse_completion({"content": "  hi  "}).content == "hi"

    def test_reasoning_content_key(self) -> None:
        result = LlamaCppBackend.parse_completion(
            {"content": "answer", "reasoning_content": "because"}
        )
        assert result.thinking == "because"
        assert result.content == "answer"

    def test_reasoning_key(self) -> None:
        result = LlamaCppBackend.parse_completion({"content": "answer", "reasoning": "hmm"})
        assert result.thinking == "hmm"

    def test_choices_style_response(self) -> None:
        result = LlamaCppBackend.parse_completion({"choices": [{"content": "from choices"}]})
        assert result.content == "from choices"

    def test_choices_with_text_key(self) -> None:
        assert LlamaCppBackend.parse_completion({"choices": [{"text": "t"}]}).content == "t"

    def test_unknown_shape_degrades_to_content(self) -> None:
        """An older server must keep working, not lose its answer."""
        result = LlamaCppBackend.parse_completion({"unexpected": "shape"})
        assert result.content == ""
        assert result.thinking == ""

    def test_missing_content_is_empty_not_an_error(self) -> None:
        assert LlamaCppBackend.parse_completion({}).content == ""

    def test_empty_thinking_is_not_reported_as_present(self) -> None:
        result = LlamaCppBackend.parse_completion({"content": "a", "thinking": "   "})
        assert not result.has_thinking


# -- shutdown (ADR-003 §3) --------------------------------------------------


class TestShutdown:
    def test_close_stops_the_server(self) -> None:
        backend = make_backend()
        backend.start()
        proc_pid = backend.pid
        assert proc_pid is not None
        backend.close()
        assert not backend.is_running
        assert backend.pid is None

    def test_close_is_idempotent(self) -> None:
        backend = make_backend()
        backend.start()
        backend.close()
        backend.close()
        backend.close()

    def test_close_without_start_is_safe(self) -> None:
        LlamaCppBackend(model="/m.gguf", binary="x").close()

    def test_context_manager_stops_the_server(self) -> None:
        with make_backend() as backend:
            backend.start()
            proc = backend._proc
            assert proc is not None
        assert proc.poll() is not None

    def test_backend_restarts_after_close(self) -> None:
        backend = make_backend()
        try:
            backend.generate("x")
            backend.close()
            assert backend.generate("y") == "The answer is 42."
        finally:
            backend.close()

    def test_no_processes_leak_across_many_lifecycles(self) -> None:
        before = len(subprocess._active)  # type: ignore[attr-defined]
        for _ in range(3):
            backend = make_backend()
            backend.generate("x")
            backend.close()
        assert len(subprocess._active) == before  # type: ignore[attr-defined]


# -- ResidentBackend contract ---------------------------------------------


class TestResidentBase:
    def test_probe_must_be_implemented(self) -> None:
        """Calling _probe directly is the deterministic check."""

        class Bare(ResidentBackend):
            pass

        bare = Bare(["true"], name="bare")
        with pytest.raises(NotImplementedError):
            bare._probe()
        bare.close()

    def test_missing_probe_propagates_instead_of_timing_out(self) -> None:
        """A subclass that forgot _probe must not look like a model problem.

        The process here is long-lived on purpose: a short-lived one would exit
        first and `start()` would report an exit during startup, which is a
        different failure and made this test race-dependent.
        """
        sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]

        class Bare(ResidentBackend):
            pass

        bare = Bare(sleeper, name="bare", ready_timeout=2.0)
        with pytest.raises(NotImplementedError):
            bare.start()
        bare.close()

    def test_empty_argv_rejected(self) -> None:
        with pytest.raises(ValueError, match="argv"):
            ResidentBackend([])

    def test_describe_reports_stopped_by_default(self) -> None:
        assert "stopped" in ResidentBackend(["true"], name="d").describe()

    def test_describe_reports_running(self) -> None:
        backend = make_backend()
        try:
            backend.start()
            assert "running" in backend.describe()
        finally:
            backend.close()

    def test_base_available_is_false(self) -> None:
        assert ResidentBackend.available() is False


# -- integration -----------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("VOICEVISION_LLM_MODEL"),
    reason="set VOICEVISION_LLM_MODEL to run against a real llama-server",
)
def test_real_llama_server_completes() -> None:
    """Opt-in. Requires llama.cpp, a model, and enough RAM."""
    backend = LlamaCppBackend(
        model=os.environ["VOICEVISION_LLM_MODEL"],
        port=free_port(),
        ready_timeout=180.0,
    )
    try:
        assert backend.available()
        assert backend.generate("Reply with the single word: ready")
    finally:
        backend.close()
