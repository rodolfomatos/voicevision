"""Errors raised by voicevision.

Kept at package top level: callers need to catch these, and a caller should
never have to import a specific backend's file to do so.

Version: 2.0.0 (M1 Core Abstraction)
"""

from __future__ import annotations

from typing import Any

__all__ = [
    # Base
    "VoiceVisionError",
    # Configuration
    "ConfigurationError",
    # Provider
    "ProviderError",
    "ProviderUnavailableError",
    "ProviderTimeoutError",
    "ProviderConfigError",
    "ProviderRuntimeError",
    # Pipeline
    "PipelineError",
    "PipelineCancelledError",
    "PipelineInterruptedError",
    "PipelineStateError",
    # Audio
    "AudioError",
    "AudioFormatError",
    "AudioDeviceError",
    # Model
    "ModelError",
    "ModelDownloadError",
    "ModelLoadError",
    # Legacy aliases (for backwards compatibility)
    "BackendNotAvailableError",
    "BackendExecutionError",
]


# =============================================================================
# Base
# =============================================================================

class VoiceVisionError(Exception):
    """Base class for every error this package raises deliberately."""

    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.context = context or {}
        self.cause = cause
        super().__init__(message)


# =============================================================================
# Configuration Errors
# =============================================================================

class ConfigurationError(VoiceVisionError):
    """Configuration is invalid, or names a provider that is not registered.

    Raised at facade/pipeline construction (fail fast), not on first use.
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: Any = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.field = field
        self.value = value
        ctx = context or {}
        if field:
            ctx["field"] = field
        if value is not None:
            ctx["value"] = str(value)
        super().__init__(message, context=ctx, cause=cause)


# =============================================================================
# Provider Errors
# =============================================================================

class ProviderError(VoiceVisionError):
    """Base class for provider-level failures."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        modality: str,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.provider = provider
        self.modality = modality
        ctx = context or {}
        ctx.update({"provider": provider, "modality": modality})
        super().__init__(message, context=ctx, cause=cause)


class ProviderUnavailableError(ProviderError):
    """A provider's executable or dependency is missing.

    Raised *before* any work is attempted, so the operator gets the install
    instruction rather than a FileNotFoundError traceback.
    """

    def __init__(
        self,
        provider: str,
        modality: str,
        install_hint: str,
        *,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.install_hint = install_hint
        ctx = context or {}
        ctx["install_hint"] = install_hint
        super().__init__(
            f"Provider {provider!r} ({modality}) is not available. {install_hint}",
            provider=provider,
            modality=modality,
            context=ctx,
            cause=cause,
        )


class ProviderTimeoutError(ProviderError):
    """A provider operation timed out.

    Distinct from PipelineCancelledError — this is a deadline exceeded,
    not an external cancellation request.
    """

    def __init__(
        self,
        provider: str,
        modality: str,
        timeout: float,
        *,
        command: str | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.timeout = timeout
        self.command = command
        ctx = context or {}
        ctx["timeout"] = timeout
        if command:
            ctx["command"] = command
        super().__init__(
            f"Provider {provider!r} ({modality}) timed out after {timeout:g}s",
            provider=provider,
            modality=modality,
            context=ctx,
            cause=cause,
        )


class ProviderConfigError(ProviderError):
    """Invalid provider configuration."""

    def __init__(
        self,
        provider: str,
        modality: str,
        message: str,
        *,
        field: str | None = None,
        value: Any = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.field = field
        self.value = value
        ctx = context or {}
        if field:
            ctx["field"] = field
        if value is not None:
            ctx["value"] = str(value)
        super().__init__(
            f"Provider {provider!r} ({modality}) config error: {message}",
            provider=provider,
            modality=modality,
            context=ctx,
            cause=cause,
        )


class ProviderRuntimeError(ProviderError):
    """A provider process failed, crashed, or was killed.

    Carries enough context to diagnose without re-running by hand: the command,
    the exit code, and the tail of stderr.
    """

    def __init__(
        self,
        provider: str,
        modality: str,
        message: str,
        *,
        command: str | None = None,
        returncode: int | None = None,
        stderr: str = "",
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        ctx = context or {}
        if command:
            ctx["command"] = command
        if returncode is not None:
            ctx["returncode"] = returncode
        if stderr:
            ctx["stderr_tail"] = self._tail(stderr)
        super().__init__(
            self._format(provider, modality, message),
            provider=provider,
            modality=modality,
            context=ctx,
            cause=cause,
        )

    @staticmethod
    def _tail(text: str, limit: int = 500) -> str:
        """Last `limit` characters of `text`, where errors actually are."""
        text = text.strip()
        if len(text) <= limit:
            return text
        return "..." + text[-limit:]

    def _format(self, provider: str, modality: str, message: str) -> str:
        parts = [f"[{provider}/{modality}] {message}"]
        if self.command:
            parts.append(f"command: {self.command}")
        if self.returncode is not None:
            parts.append(f"exit code: {self.returncode}")
        if self.stderr:
            parts.append(f"stderr (tail):\n{self._tail(self.stderr)}")
        return "\n".join(parts)


# =============================================================================
# Pipeline Errors
# =============================================================================

class PipelineError(VoiceVisionError):
    """Pipeline orchestration failures."""

    def __init__(
        self,
        message: str,
        *,
        session_id: str | None = None,
        turn_id: str | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.session_id = session_id
        self.turn_id = turn_id
        ctx = context or {}
        if session_id:
            ctx["session_id"] = session_id
        if turn_id:
            ctx["turn_id"] = turn_id
        super().__init__(message, context=ctx, cause=cause)


class PipelineCancelledError(PipelineError):
    """Pipeline was cancelled via CancellationToken.

    Distinct from ProviderTimeoutError — this is an external request,
    not a deadline.
    """

    def __init__(
        self,
        message: str = "Pipeline cancelled",
        *,
        session_id: str | None = None,
        turn_id: str | None = None,
        reason: str | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.reason = reason
        ctx = context or {}
        if reason:
            ctx["reason"] = reason
        super().__init__(message, session_id=session_id, turn_id=turn_id, context=ctx, cause=cause)


class PipelineInterruptedError(PipelineError):
    """Pipeline was interrupted (barge-in).

    User started speaking during assistant response.
    """

    def __init__(
        self,
        message: str = "Pipeline interrupted by user speech",
        *,
        session_id: str | None = None,
        turn_id: str | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(
            message,
            session_id=session_id,
            turn_id=turn_id,
            context=context,
            cause=cause,
        )


class PipelineStateError(PipelineError):
    """Invalid state transition in conversation state machine."""

    def __init__(
        self,
        message: str,
        *,
        current_state: str,
        target_state: str,
        session_id: str | None = None,
        turn_id: str | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.current_state = current_state
        self.target_state = target_state
        ctx = context or {}
        ctx.update({"current_state": current_state, "target_state": target_state})
        super().__init__(
            f"Invalid state transition: {current_state} -> {target_state}. {message}",
            session_id=session_id,
            turn_id=turn_id,
            context=ctx,
            cause=cause,
        )


# =============================================================================
# Audio Errors
# =============================================================================

class AudioError(VoiceVisionError):
    """Base class for audio-related errors."""

    pass


class AudioFormatError(AudioError):
    """Audio format is invalid or unsupported."""

    def __init__(
        self,
        message: str,
        *,
        expected: str | None = None,
        actual: str | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.expected = expected
        self.actual = actual
        ctx = context or {}
        if expected:
            ctx["expected"] = expected
        if actual:
            ctx["actual"] = actual
        super().__init__(message, context=ctx, cause=cause)


class AudioDeviceError(AudioError):
    """Audio device error (capture/playback)."""

    def __init__(
        self,
        message: str,
        *,
        device: str | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.device = device
        ctx = context or {}
        if device:
            ctx["device"] = device
        super().__init__(message, context=ctx, cause=cause)


# =============================================================================
# Model Errors
# =============================================================================

class ModelError(VoiceVisionError):
    """Base class for model-related errors."""

    pass


class ModelDownloadError(ModelError):
    """Failed to download a model."""

    def __init__(
        self,
        message: str,
        *,
        model: str,
        url: str | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.model = model
        self.url = url
        ctx = context or {}
        ctx["model"] = model
        if url:
            ctx["url"] = url
        super().__init__(message, context=ctx, cause=cause)


class ModelLoadError(ModelError):
    """Failed to load a model."""

    def __init__(
        self,
        message: str,
        *,
        model: str,
        path: str | None = None,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.model = model
        self.path = path
        ctx = context or {}
        ctx["model"] = model
        if path:
            ctx["path"] = path
        super().__init__(message, context=ctx, cause=cause)


# =============================================================================
# Legacy Aliases (Backwards Compatibility)
# =============================================================================

class BackendNotAvailableError(ProviderUnavailableError):
    """Legacy alias for ProviderUnavailableError."""

    def __init__(
        self,
        backend: str,
        install_hint: str,
        *,
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        # modality unknown in legacy code, use "unknown"
        super().__init__(backend, "unknown", install_hint, context=context, cause=cause)


class BackendExecutionError(ProviderRuntimeError):
    """Legacy alias for ProviderRuntimeError."""

    def __init__(
        self,
        backend: str,
        message: str,
        *,
        command: str | None = None,
        returncode: int | None = None,
        stderr: str = "",
        context: dict[str, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(
            backend,
            "unknown",
            message,
            command=command,
            returncode=returncode,
            stderr=stderr,
            context=context,
            cause=cause,
        )
