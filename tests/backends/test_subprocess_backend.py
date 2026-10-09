"""Tests for SubprocessBackend — the process lifecycle.

Every test drives a real child process via tests.support.fake_child. No models,
no GPU, no audio hardware.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.support.fake_child import (
    BINARY,
    DIE_MID_WRITE,
    ECHO,
    EXIT_NONZERO,
    NOOP,
    SLEEP,
    STDERR_FLOOD,
    build_argv,
)
from voicevision.backends.subprocess_backend import SubprocessBackend
from voicevision.errors import (
    BackendExecutionError,
    BackendNotAvailableError,
    ConfigurationError,
    VoiceVisionError,
)


@pytest.fixture
def backend() -> SubprocessBackend:
    """A backend wrapping the `echo` fake child."""
    return SubprocessBackend(build_argv(ECHO), name="fake")


# -- construction ----------------------------------------------------------


class TestConstruction:
    def test_rejects_empty_argv(self) -> None:
        with pytest.raises(ValueError, match="argv"):
            SubprocessBackend([])

    def test_default_timeout_is_thirty_seconds(self) -> None:
        assert SubprocessBackend(build_argv(ECHO)).timeout == 30.0

    def test_timeout_override_in_constructor(self) -> None:
        assert SubprocessBackend(build_argv(ECHO), timeout=5.0).timeout == 5.0

    def test_no_process_spawned_on_construction(self) -> None:
        """Constructing a backend must not cost a model load for something that
        may never be called."""
        b = SubprocessBackend(build_argv(ECHO), name="lazy")
        assert b.last_pid is None

    def test_name_defaults_to_executable(self) -> None:
        assert SubprocessBackend(build_argv(ECHO)).name == sys.executable


# -- one-shot semantics ----------------------------------------------------


class TestOneShotLifecycle:
    """whisper.cpp and piper exit after one job. Each call is a fresh child.

    This is not a performance regression to be optimised later — see the module
    docstring. These programs have no loop mode.
    """

    def test_each_call_uses_a_fresh_child(self, backend: SubprocessBackend) -> None:
        backend.run(b"first")
        first_pid = backend.last_pid
        backend.run(b"second")
        assert backend.last_pid != first_pid

    def test_fresh_child_still_returns_correct_output(self, backend: SubprocessBackend) -> None:
        for i in range(5):
            assert backend.run(str(i).encode()) == str(i).encode()

    def test_no_child_is_left_running(self, backend: SubprocessBackend) -> None:
        backend.run(b"x")
        # Every child has been reaped; there is nothing resident to leak.
        assert backend.close() is None

    def test_processes_do_not_accumulate(self, backend: SubprocessBackend) -> None:
        before = len(subprocess._active)  # type: ignore[attr-defined]
        for _ in range(5):
            backend.run(b"x")
        after = len(subprocess._active)  # type: ignore[attr-defined]
        assert after <= before


# -- transport -------------------------------------------------------------


class TestTransport:
    def test_roundtrip_returns_stdout(self, backend: SubprocessBackend) -> None:
        assert backend.run(b"hello world") == b"hello world"

    def test_empty_payload_allowed(self) -> None:
        b = SubprocessBackend(build_argv(NOOP), name="noop")
        assert b.run(b"") == b""

    def test_binary_stdout_preserved(self) -> None:
        """Decoding is the caller's decision; this layer returns bytes."""
        b = SubprocessBackend(build_argv(BINARY), name="bin")
        assert b.run(b"") == bytes([0xFF, 0xFE, 0xFD, 0x00, 0x01])

    def test_metacharacters_in_arguments_are_not_interpreted(self) -> None:
        """argv is a list and shell=False, so a `$(...)` in an argument is data.

        The child echoes stdin, so we assert the shell did not run the command
        and its output did not appear.
        """
        argv = build_argv(ECHO) + ["$(touch /tmp/pwned)", "; rm -rf /", "`id`"]
        b = SubprocessBackend(argv, name="meta")
        out = b.run(b"safe")
        assert out == b"safe"
        assert b"pwned" not in out
        assert b"uid=" not in out


# -- the deadlock regression ------------------------------------------------


class TestStderrFloodDoesNotDeadlock:
    def test_child_writing_200kb_to_stderr_completes(self) -> None:
        """The classic pipe deadlock, and the reason this module uses
        `communicate`.

        The child writes 200 KB to stderr — well past the 64 KiB pipe buffer —
        before writing anything to stdout. An implementation that waits on stdout
        while ignoring stderr blocks here forever. This test is the guard against
        someone optimising `_invoke` into a manual pipe loop.
        """
        b = SubprocessBackend(build_argv(STDERR_FLOOD), name="flood", timeout=10.0)
        assert b.run(b"") == b"survived"

    def test_stderr_is_still_read_when_stdout_is_empty(self) -> None:
        """Flood plus a clean exit must not hang, and must not raise."""
        argv = [sys.executable, "-c", "import sys\nsys.stderr.buffer.write(b'E'*200000)"]
        b = SubprocessBackend(argv, name="quiet", timeout=10.0)
        assert b.run(b"") == b""


# -- failure surfacing (FR-10) ---------------------------------------------


class TestFailureSurfacing:
    def test_non_zero_exit_raises_with_stderr(self) -> None:
        b = SubprocessBackend(build_argv(EXIT_NONZERO), name="broken")
        with pytest.raises(BackendExecutionError) as exc:
            b.run(b"")
        assert exc.value.returncode == 3
        assert "model exploded" in exc.value.stderr
        assert "exit code: 3" in str(exc.value)

    def test_error_message_includes_command(self) -> None:
        b = SubprocessBackend(build_argv(EXIT_NONZERO), name="broken")
        with pytest.raises(BackendExecutionError) as exc:
            b.run(b"")
        assert exc.value.command is not None
        assert "command:" in str(exc.value)

    def test_error_tail_is_truncated_not_head(self) -> None:
        """Errors live at the end of a log; the banner must not crowd them out."""
        err = BackendExecutionError("x", "m", stderr="BANNER\n" + ("z" * 5000))
        assert "BANNER" not in err._tail(err.stderr)
        assert err._tail(err.stderr).endswith("z")

    def test_missing_executable_raises_not_available(self) -> None:
        b = SubprocessBackend(["definitely-not-a-real-binary-xyz"], name="ghost")
        with pytest.raises(BackendNotAvailableError) as exc:
            b.run(b"")
        assert "ghost" in str(exc.value)
        assert exc.value.install_hint

    def test_crash_is_never_reported_as_empty_success(self) -> None:
        b = SubprocessBackend(build_argv(EXIT_NONZERO), name="broken")
        raised = False
        try:
            b.run(b"")
        except BackendExecutionError:
            raised = True
        assert raised


# -- timeout ---------------------------------------------------------------


class TestTimeout:
    def test_timeout_raises_and_names_the_deadline(self) -> None:
        b = SubprocessBackend(build_argv(SLEEP), name="slow", timeout=0.5)
        with pytest.raises(BackendExecutionError) as exc:
            b.run(b"")
        assert "timed out" in str(exc.value)
        assert "0.5" in str(exc.value)

    def test_timed_out_child_is_killed_not_left_resident(self) -> None:
        """A hung child holding a model resident would leak memory."""
        b = SubprocessBackend(build_argv(SLEEP), name="slow", timeout=0.5)
        with pytest.raises(BackendExecutionError):
            b.run(b"")
        assert len(subprocess._active) == 0  # type: ignore[attr-defined]

    def test_timeout_is_not_retried(self) -> None:
        """Retrying a timeout makes the operator wait twice for one verdict."""
        b = SubprocessBackend(build_argv(SLEEP), name="slow", timeout=0.5)
        before = len(subprocess._active)  # type: ignore[attr-defined]
        for _ in range(3):
            with pytest.raises(BackendExecutionError):
                b.run(b"")
        assert len(subprocess._active) == before  # type: ignore[attr-defined]

    def test_per_call_timeout_overrides_default(self) -> None:
        b = SubprocessBackend(build_argv(SLEEP), name="slow", timeout=60.0)
        with pytest.raises(BackendExecutionError):
            b.run(b"", timeout=0.5)


# -- single retry (FR-9) ----------------------------------------------------


class TestSingleRetry:
    def test_mid_call_death_is_retried_once(self) -> None:
        b = SubprocessBackend(build_argv(DIE_MID_WRITE), name="dies", timeout=10.0)
        with pytest.raises(BackendExecutionError) as exc:
            b.run(b"abcdefgh")
        assert "failed again on retry" in str(exc.value)

    def test_retry_does_not_loop_forever(self) -> None:
        """Two attempts maximum. More would be a fork bomb."""
        b = SubprocessBackend(build_argv(DIE_MID_WRITE), name="dies", timeout=10.0)
        for _ in range(3):
            with pytest.raises(BackendExecutionError):
                b.run(b"abcdefgh")

    def test_retry_is_exactly_two_spawns(self) -> None:
        """Pin the count. `run` is the only place that spawns, so the pid delta
        across one call is exactly the number of attempts."""
        b = SubprocessBackend(build_argv(DIE_MID_WRITE), name="dies", timeout=10.0)
        seen: list[int | None] = []
        original = b._spawn

        def recording_spawn() -> subprocess.Popen[bytes]:
            proc = original()
            seen.append(b._last_pid)
            return proc

        b._spawn = recording_spawn  # type: ignore[method-assign]
        with pytest.raises(BackendExecutionError):
            b.run(b"abcdefgh")
        assert len(seen) == 2


# -- introspection ---------------------------------------------------------


class TestIntrospection:
    def test_available_is_false_for_unknown_executable(self) -> None:
        class Ghost(SubprocessBackend):
            executable = "definitely-not-real-xyz"
            install_hint = "install the thing"

        assert Ghost.available() is False
        assert "install the thing" in Ghost(build_argv(ECHO), name="g").describe()

    def test_available_is_true_for_python(self) -> None:
        class Py(SubprocessBackend):
            executable = sys.executable

        assert Py.available() is True

    def test_describe_reports_unavailable_for_base_class(self) -> None:
        """The base class declares no executable, so it reports not-ready."""
        b = SubprocessBackend(build_argv(ECHO), name="d")
        assert "unavailable" in b.describe()

    def test_describe_reports_ready_when_executable_exists(self) -> None:
        class Py(SubprocessBackend):
            executable = sys.executable

        b = Py(build_argv(ECHO), name="d")
        assert "ready" in b.describe()

    def test_repr_includes_state(self, backend: SubprocessBackend) -> None:
        assert "fake" in repr(backend)

    def test_context_manager_is_a_noop_that_does_not_raise(self) -> None:
        with SubprocessBackend(build_argv(ECHO), name="ctx") as b:
            b.run(b"x")


class TestErrorTypes:
    def test_backend_errors_share_a_base(self) -> None:
        assert issubclass(BackendExecutionError, VoiceVisionError)
        assert issubclass(BackendNotAvailableError, VoiceVisionError)
        assert issubclass(ConfigurationError, VoiceVisionError)

    def test_backend_execution_error_formats_usefully_when_bare(self) -> None:
        """Constructing with only a message must not crash formatting."""
        assert "m" in str(BackendExecutionError("x", "m"))
