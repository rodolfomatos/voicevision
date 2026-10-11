"""Supervision for resident (daemon) model processes.

Distinct from SubprocessBackend, which owns one-shot children. A daemon is the
opposite problem: it starts once, must become *ready* before it can be used,
stays resident to keep a model loaded, and has to be shut down in the right
order when the container goes away (ADR-003 §3).

Kept separate rather than folded into SubprocessBackend because the two have
almost nothing in common beyond spawning a process. Forcing the LLM daemon
through a pipe-transport base class would mean overriding most of it.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import tempfile
import time
from typing import IO, ClassVar

from voicevision.errors import BackendExecutionError, BackendNotAvailableError

#: How often to poll a readiness endpoint.
POLL_INTERVAL = 0.25

#: Default startup budget. Loading a 1.7B model from disk on a Raspberry Pi is
#: slow; on a laptop this is generous. Both are configurable.
DEFAULT_READY_TIMEOUT = 120.0

#: Grace period between SIGTERM and SIGKILL.
KILL_GRACE_SECONDS = 5.0


def spawn_process(
    argv: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    name: str,
    stderr: int | IO[bytes] | None = subprocess.PIPE,
) -> subprocess.Popen[bytes]:
    """Start a process.

    `stderr` may be a file object. ResidentBackend passes a temporary file
    rather than a pipe: a daemon runs for hours, so its diagnostics have to be
    readable at any moment without killing it, and an unread pipe would fill and
    block the process.
    """
    try:
        return subprocess.Popen(  # noqa: S603 - argv list, never shell=True
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=stderr,
            cwd=cwd,
            env=env,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise BackendNotAvailableError(
            name, "Install the backend binary; see install_hint."
        ) from exc
    except OSError as exc:
        raise BackendExecutionError(
            name, f"could not start process: {exc}", command=" ".join(argv)
        ) from exc


def force_kill(proc: subprocess.Popen[bytes]) -> None:
    """SIGTERM, then SIGKILL after a grace period.

    Ordering matters in a container: the model must release GPU memory before
    the process disappears, and a hard kill skips that (ADR-003 §3).
    """
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=KILL_GRACE_SECONDS)


class ResidentBackend:
    """Base class for a long-lived child process with a readiness probe.

    Subclasses implement `_probe()` to decide whether the process can serve
    traffic yet. Returning immediately and assuming success is a bug: the first
    request would race model loading and fail in a way that looks like a
    transport problem.
    """

    executable: ClassVar[str] = ""
    install_hint: ClassVar[str] = "Install the backend binary and its model files."

    #: Seconds allowed between spawn and readiness.
    default_ready_timeout: ClassVar[float] = DEFAULT_READY_TIMEOUT

    def __init__(
        self,
        argv: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        ready_timeout: float | None = None,
        name: str | None = None,
    ) -> None:
        if not argv:
            raise ValueError("argv must not be empty")
        self._argv = list(argv)
        self._cwd = cwd
        self._env = env
        self._ready_timeout = self.default_ready_timeout if ready_timeout is None else ready_timeout
        self._name = name or argv[0]
        self._proc: subprocess.Popen[bytes] | None = None
        # stderr goes to a file, not a pipe. The daemon runs for hours; an
        # unread pipe fills, the process blocks writing to it, and the result
        # looks like a hang with no diagnostics. A file can be read at any
        # moment without touching the process.
        self._log: IO[bytes] | None = None

    # -- introspection ----------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def command_line(self) -> str:
        return " ".join(self._argv)

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    @property
    def ready_timeout(self) -> float:
        return self._ready_timeout

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @classmethod
    def available(cls) -> bool:
        import shutil

        return bool(cls.executable) and shutil.which(cls.executable) is not None

    def describe(self) -> str:
        state = "running" if self.is_running else "stopped"
        return f"{self._name} [{state}]"

    # -- lifecycle --------------------------------------------------------

    def _probe(self) -> bool:
        """Whether the process can serve traffic. Subclasses must implement."""
        raise NotImplementedError

    def start(self) -> None:
        """Spawn the process and block until it is ready, or raise.

        Distinguishes two failures an operator must treat differently:
        the binary is missing (install problem) versus the server never became
        healthy (model, memory, or configuration problem).
        """
        if self.is_running:
            return

        # Lifetime is the backend instance's, not start()'s, so a `with` block
        # would close it while the daemon is still writing to it.
        self._log = tempfile.TemporaryFile()  # noqa: SIM115
        proc = spawn_process(
            self._argv,
            cwd=self._cwd,
            env=self._env,
            name=self._name,
            stderr=self._log,
        )
        self._proc = proc

        deadline = time.monotonic() + self._ready_timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stderr = self.server_log()
                self._proc = None
                raise BackendExecutionError(
                    self._name,
                    f"process exited during startup with code {proc.returncode}",
                    command=self.command_line,
                    returncode=proc.returncode,
                    stderr=stderr,
                )
            try:
                if self._probe():
                    return
            except NotImplementedError:
                # A subclass that never implemented _probe is a bug in this
                # package. Swallowing it would turn a clear error into a
                # readiness timeout that looks like a model problem.
                self.close()
                raise
            except Exception:  # noqa: BLE001 - a failed probe means "not yet"
                pass
            time.sleep(POLL_INTERVAL)

        # Timed out. Take the process down rather than leaving a half-started
        # model resident, and report the stderr it produced getting there.
        stderr = self.server_log()
        self.close()
        raise BackendExecutionError(
            self._name,
            f"did not become ready within {self._ready_timeout:g}s "
            "(process still running, health endpoint never returned success). "
            "Check the model path, available memory, and the server's stderr.",
            command=self.command_line,
            stderr=stderr,
        )

    def ensure_running(self) -> None:
        """Start the process if it is not currently serving."""
        if not self.is_running:
            self.start()
            return
        try:
            if self._probe():
                return
        except NotImplementedError:
            raise
        except Exception:  # noqa: BLE001 - a failed probe means "not ready"
            pass
        # Alive but not answering. Restart once; a wedged server is not
        # something to keep using.
        self.close()
        self.start()

    def server_log(self, limit: int = 2000) -> str:
        """Tail of the daemon's stderr, for diagnostics.

        Reads from the log file at its current offset so this is safe to call
        repeatedly while the process is alive.
        """
        if self._log is None:
            return ""
        try:
            self._log.seek(0, os.SEEK_END)
            size = self._log.tell()
            self._log.seek(max(0, size - limit))
            data = self._log.read()
        except (OSError, ValueError):
            return ""
        return data.decode("utf-8", errors="replace")

    def close(self) -> None:
        """Shut the process down, escalating to SIGKILL if it hangs.

        Idempotent, and safe to call when nothing was ever started.
        """
        proc = self._proc
        log = self._log
        self._proc = None
        self._log = None
        if proc is not None:
            force_kill(proc)
        if log is not None:
            with contextlib.suppress(OSError):
                log.close()

    def __enter__(self) -> ResidentBackend:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self._name!r} running={self.is_running}>"
