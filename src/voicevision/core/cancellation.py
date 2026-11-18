"""Unified CancellationToken for voicevision.

Provides a unified cancellation mechanism that propagates through all providers,
pipeline stages, subprocesses, and async operations.

Version: 1.0.0 (M1 Core Abstraction)
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Callable, Coroutine
from typing import Any


class CancellationToken:
    """Unified cancellation token for sync and async operations.

    Features:
    - Thread-safe cancellation flag
    - Callback registration for immediate notification
    - Child tokens that cancel when parent cancels
    - Timeout-based auto-cancellation
    - Linking to other tokens
    - Context manager support
    - Async wait support
    """

    _none_instance: CancellationToken | None = None

    def __init__(self) -> None:
        self._cancelled = False
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[], None]] = []
        self._children: list[CancellationToken] = []
        self._sync_event = threading.Event()
        self._async_event: asyncio.Event | None = None

    @classmethod
    def none(cls) -> CancellationToken:
        """Singleton never-cancelled token."""
        if cls._none_instance is None:
            cls._none_instance = CancellationToken()
            # Make it impossible to cancel
            cls._none_instance.cancel = lambda: None  # type: ignore[method-assign]
        return cls._none_instance

    @property
    def cancelled(self) -> bool:
        """Whether this token has been cancelled (read-only)."""
        return self._cancelled

    def cancel(self) -> None:
        """Trigger cancellation. Notifies all callbacks and children."""
        with self._lock:
            if self._cancelled:
                return
            self._cancelled = True
            self._sync_event.set()
            callbacks = list(self._callbacks)
            children = list(self._children)

        for callback in callbacks:
            with contextlib.suppress(Exception):
                callback()

        for child in children:
            child.cancel()

        if self._async_event is not None:
            self._async_event.set()

    def throw_if_cancelled(self) -> None:
        """Raise PipelineCancelled if cancelled."""
        if self._cancelled:
            from voicevision.errors import PipelineCancelledError
            raise PipelineCancelledError("Operation cancelled")

    def on_cancel(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when cancelled.

        If already cancelled, callback is invoked immediately.
        """
        with self._lock:
            if self._cancelled:
                with contextlib.suppress(Exception):
                    callback()
                return
            self._callbacks.append(callback)

    def link(self, other: CancellationToken) -> None:
        """Link this token to another: cancels when other cancels."""
        other.on_cancel(self.cancel)

    def child(self) -> CancellationToken:
        """Create a child token that cancels when this token cancels."""
        child = CancellationToken()
        with self._lock:
            self._children.append(child)
        self.on_cancel(child.cancel)
        return child

    def with_timeout(self, seconds: float) -> CancellationToken:
        """Create a child token that auto-cancels after timeout."""
        child = self.child()

        def _timeout() -> None:
            time.sleep(seconds)
            child.cancel()

        thread = threading.Thread(target=_timeout, daemon=True)
        thread.start()
        return child

    # -- Context manager ------------------------------------------------------

    def __enter__(self) -> CancellationToken:
        return self

    def __exit__(self, *exc: object) -> None:
        self.cancel()

    # -- Async support --------------------------------------------------------

    async def wait(self) -> None:
        """Wait asynchronously for cancellation."""
        if self._cancelled:
            return
        if self._async_event is None:
            self._async_event = asyncio.Event()
        await self._async_event.wait()

    async def shield(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Run coroutine, but cancel it if this token is cancelled."""
        if self._cancelled:
            from voicevision.errors import PipelineCancelledError
            raise PipelineCancelledError("Already cancelled")

        async def _wrapped() -> Any:
            try:
                return await coro
            except asyncio.CancelledError:
                raise
            except Exception:
                raise

        task = asyncio.create_task(_wrapped())

        async def _cancel_on_token() -> None:
            await self.wait()
            task.cancel()

        cancel_task = asyncio.create_task(_cancel_on_token())
        try:
            return await task
        finally:
            cancel_task.cancel()

    def _get_async_event(self) -> asyncio.Event:
        """Get or create async event (lazy initialization)."""
        if self._async_event is None:
            self._async_event = asyncio.Event()
        return self._async_event

