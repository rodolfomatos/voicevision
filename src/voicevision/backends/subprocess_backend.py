"""Subprocess-backed model runtime.

One model per child process, pipes for transport, supervised by this class.
See docs/ADR-002-subprocess-backends.md for why models are not linked into this
process.

## One-shot semantics

`whisper.cpp` and `piper` are *not* daemons. They read their input, write their
output, and exit. There is no mode in which they wait for a second request, so
a caller cannot keep one alive between calls — `subprocess.communicate` closes
stdin when it finishes, and the child sees EOF and exits.

This class therefore spawns a fresh child per call and reaps it afterwards.
That is not an optimisation left on the table; it is what these programs are.
Process spawn cost (~50-100 ms) is the price, and it is paid against cheap
models. The expensive model — the LLM — is a resident daemon reached over HTTP
and supervised separately, which is where warm reuse actually matters.

Do not add a keep-alive here. It cannot work, and the attempt would deadlock on
the second call.

## Why `communicate`

`communicate` reads stdout and stderr concurrently. That is what prevents the
classic deadlock where a child fills its stderr pipe buffer and blocks forever
while the parent waits on stdout. Rewriting `_invoke` as a manual
`stdin.write` / `stdout.read` loop reintroduces that deadlock. There is a
regression test for it (test_stderr_flood_does_not_deadlock) — read it before
touching this code.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from typing import ClassVar

from voicevision.errors import BackendExecutionError, BackendNotAvailableError

#: Grace period between SIGTERM and SIGKILL.
_KILL_GRACE_SECONDS = 2.0

#: Default per-call deadline. Overridable per call or via constructor.
DEFAULT_TIMEOUT = 30.0


class SubprocessBackend:
    """Base class for backends that shell out to a one-shot model executable.

    Subclasses declare the executable and parse whatever comes back; this class
    guarantees that the call completes within a deadline and that failures are
    legible.
    """

    #: Executable name, resolved on PATH. Subclasses must override.
    executable: ClassVar[str] = ""

    #: What the operator should do when `available()` is False.
    install_hint: ClassVar[str] = "Install the backend and its model files."

    #: Default per-call deadline for this backend, in seconds.
    default_timeout: ClassVar[float] = DEFAULT_TIMEOUT

    def __init__(
        self,
        argv: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        name: str | None = None,
    ) -> None:
        if not argv:
            raise ValueError("argv must not be empty")
        self._argv = list(argv)
        self._cwd = cwd
        self._env = env
        self._timeout = self.default_timeout if timeout is None else timeout
        self._name = name or argv[0]
        self._last_pid: int | None = None

        # One child per call, but the counter below still matters: two
        # concurrent calls would interleave spawn accounting and make the
        # "exactly one retry" guarantee unobservable. Serialise regardless.
        self._lock = threading.Lock()

    # -- introspection ----------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def timeout(self) -> float:
        return self._timeout

    @property
    def last_pid(self) -> int | None:
        """Pid of the most recent child. Retained for diagnostics only."""
        return self._last_pid

    @classmethod
    def available(cls) -> bool:
        """Whether this backend's executable can be found.

        Called before any work so the operator gets `install_hint` instead of a
        FileNotFoundError traceback.
        """
        return bool(cls.executable) and shutil.which(cls.executable) is not None

    def describe(self) -> str:
        """One-line summary for diagnostics and `make doctor`."""
        state = "ready" if self.available() else f"unavailable: {self.install_hint}"
        return f"{self._name} [{state}]"

    # -- process lifecycle -------------------------------------------------

    def _spawn(self) -> subprocess.Popen[bytes]:
        try:
            proc = subprocess.Popen(  # noqa: S603 - argv list, never shell=True
                self._argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._cwd,
                env=self._env,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise BackendNotAvailableError(self._name, self.install_hint) from exc
        except OSError as exc:
            raise BackendExecutionError(
                self._name,
                f"could not start process: {exc}",
                command=self.command_line,
            ) from exc
        self._last_pid = proc.pid
        return proc

    @property
    def command_line(self) -> str:
        return " ".join(self._argv)

    # -- invocation --------------------------------------------------------

    def _invoke(self, payload: bytes, timeout: float) -> bytes:
        """Spawn a child, send `payload`, return stdout. Runs one attempt."""
        proc = self._spawn()
        command = self.command_line

        try:
            stdout, stderr = proc.communicate(input=payload, timeout=timeout)
        except subprocess.TimeoutExpired:
            # The child is still running and holding a model resident. Leaving
            # it alive would leak memory, but killing it here hides which call
            # was slow — the operator gets a message instead of a mystery.
            self._force_kill(proc)
            raise BackendExecutionError(
                self._name,
                f"timed out after {timeout:g}s",
                command=command,
                returncode=proc.returncode,
            ) from None

        stderr_text = stderr.decode("utf-8", errors="replace")

        if proc.returncode != 0:
            raise BackendExecutionError(
                self._name,
                "process exited non-zero",
                command=command,
                returncode=proc.returncode,
                stderr=stderr_text,
            )

        return stdout

    def run(self, payload: bytes = b"", *, timeout: float | None = None) -> bytes:
        """Run one request and return stdout.

        A child that crashes is retried exactly once with a fresh process. A
        second failure is surfaced — an unbounded respawn loop turns a broken
        model into a fork bomb.
        """
        effective_timeout = self._timeout if timeout is None else timeout

        with self._lock:
            try:
                return self._invoke(payload, effective_timeout)
            except BackendExecutionError as exc:
                first_error = exc

            # A timeout is a verdict about the workload, not a crash. Retrying
            # only makes the operator wait twice as long for the same answer.
            if not self._is_retryable(first_error):
                raise first_error

            try:
                return self._invoke(payload, effective_timeout)
            except BackendExecutionError as second:
                raise BackendExecutionError(
                    self._name,
                    "failed again on retry",
                    command=second.command,
                    returncode=second.returncode,
                    stderr=second.stderr,
                ) from first_error

    @staticmethod
    def _is_retryable(exc: BackendExecutionError) -> bool:
        """Only retry when the child was the problem, not when the clock was."""
        return "timed out" not in exc.args[0] if exc.args else True

    # -- teardown ----------------------------------------------------------

    @staticmethod
    def _force_kill(proc: subprocess.Popen[bytes]) -> None:
        """SIGTERM, then SIGKILL after a grace period."""
        if proc.poll() is None:
            proc.terminate()
            # contextlib.suppress cannot express this: the timeout is not an
            # error to ignore, it is the signal to escalate to SIGKILL.
            try:  # noqa: SIM105
                proc.wait(timeout=_KILL_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=_KILL_GRACE_SECONDS)

    def close(self) -> None:
        """No long-lived child to stop. Present for interface symmetry and to
        let the facade close everything uniformly."""
        return

    def __enter__(self) -> SubprocessBackend:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self._name!r}>"
