"""Errors raised by voicevision backends.

Kept at package top level rather than inside a backend module: callers need to
catch these, and a caller should never have to import a specific backend's file
to do so.
"""

from __future__ import annotations

__all__ = [
    "VoiceVisionError",
    "BackendNotAvailableError",
    "BackendExecutionError",
    "ConfigurationError",
]


class VoiceVisionError(Exception):
    """Base class for every error this package raises deliberately."""


class BackendNotAvailableError(VoiceVisionError):
    """A backend's executable or dependency is missing.

    Raised *before* any work is attempted, so the operator gets the install
    instruction rather than a FileNotFoundError traceback.
    """

    def __init__(self, backend: str, install_hint: str) -> None:
        self.backend = backend
        self.install_hint = install_hint
        super().__init__(f"Backend {backend!r} is not available. {install_hint}")


class BackendExecutionError(VoiceVisionError):
    """A backend process failed, timed out, or was killed.

    Carries enough context to diagnose without re-running by hand: the command,
    the exit code, and the tail of stderr.
    """

    def __init__(
        self,
        backend: str,
        message: str,
        *,
        command: str | None = None,
        returncode: int | None = None,
        stderr: str = "",
    ) -> None:
        self.backend = backend
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(self._format(backend, message))

    @staticmethod
    def _tail(text: str, limit: int = 500) -> str:
        """Last `limit` characters of `text`, which is where errors actually are.

        Model tools put their banner at the start and the failure at the end.
        """
        text = text.strip()
        if len(text) <= limit:
            return text
        return "..." + text[-limit:]

    def _format(self, backend: str, message: str) -> str:
        parts = [f"[{backend}] {message}"]
        if self.command:
            parts.append(f"command: {self.command}")
        if self.returncode is not None:
            parts.append(f"exit code: {self.returncode}")
        if self.stderr:
            parts.append(f"stderr (tail):\n{self._tail(self.stderr)}")
        return "\n".join(parts)


class ConfigurationError(VoiceVisionError):
    """Configuration is invalid, or names a backend that is not registered.

    Raised at facade construction (fail fast), not on first use.
    """
