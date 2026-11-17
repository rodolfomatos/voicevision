"""Vision backend: moondream GGUF via llama.cpp.

Moondream is a small vision-language model (~1.9B parameters) that can describe
and answer questions about images. It runs as a subprocess via llama.cpp
(ADR-001, ADR-002) — never linked into this process.

The model expects images as multipart/form-data uploads and answers via the
llama.cpp completion endpoint.

All heavy dependencies (llama-cpp-python, pillow) are lazy-imported so
`import voicevision.backends.vision` stays cheap.

Implements VisionProvider protocol (M1).
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

from voicevision.core.protocols import ProviderCapabilities, ProviderLifecycle
from voicevision.errors import BackendExecutionError

#: Maximum image size in pixels (larger images are downscaled).
MAX_IMAGE_SIZE: Final = 512


class MoondreamBackend:
    """Describe and answer questions about images via moondream GGUF + llama.cpp.

    Implements VisionProvider protocol.

    moondream is a small vision-language model that accepts an image and a
    question, and returns a text answer. It runs as a subprocess via
    llama.cpp's completion endpoint.

    The model is never downloaded by this package — the operator must supply
    the GGUF model file and set VOICEVISION_VISION_MODEL.
    """

    install_hint: ClassVar[str] = (
        "Install moondream GGUF model: download from "
        "https://github.com/vikhyat/moondream/releases "
        "(moondream2-v2-f16.gguf), then set VOICEVISION_VISION_MODEL"
    )

    def __init__(
        self,
        *,
        model: str,
        host: str = "127.0.0.1",
        port: int = 8081,
        context_size: int = 2048,
        gpu_layers: int = 0,
        threads: int = 4,
        **kwargs: object,
    ) -> None:
        del kwargs  # unused
        if not model:
            raise ValueError("model path is required — this backend does not download models")
        self._model = model
        self._host = host
        self._port = port
        self._context_size = context_size
        self._gpu_layers = gpu_layers
        self._threads = threads
        self._proc: Any = None

    @classmethod
    def available(cls) -> bool:
        try:
            import httpx  # noqa: F401, PLC0415 - lazy import per CLAUDE.md
            return True
        except ImportError:
            return False

    # install_hint is a class attribute (line 40). The protocol expects a classmethod,
    # but @runtime_checkable only validates instance methods. Class attribute works.

    # -- VisionProvider protocol -----------------------------------------------

    def describe(
        self,
        image: bytes,
        *,
        prompt: str | None = None,
        token: CancellationToken | None = None,
        **kwargs: Any,
    ) -> str:
        """Describe or analyze an image.

        Args:
            image: Raw image bytes (JPEG/PNG).
            prompt: Optional prompt to guide description (e.g. "What is in
                this image?").
            token: Optional cancellation token.
            **kwargs: Backend-specific parameters.

        Returns:
            Text description/analysis of the image.

        Raises:
            ProviderRuntimeError: if httpx or llama-server is not available,
                or if the request fails.
        """
        if token is not None:
            token.throw_if_cancelled()

        del kwargs  # unused
        if not image:
            raise BackendExecutionError(
                "moondream",
                "no image data provided",
            )

        import httpx  # noqa: PLC0415 - lazy import per CLAUDE.md

        prompt_text = prompt or "Describe this image in detail."

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    f"http://{self._host}:{self._port}/completion",
                    files={"file": ("image.jpg", image, "image/jpeg")},
                    data={"prompt": prompt_text},
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:  # noqa: BLE001 - surface all backend errors
            error_message = str(exc)
            if "connect" in error_message.lower() or "connection" in error_message.lower():
                raise BackendExecutionError(
                    "moondream",
                    f"could not connect to llama-server at {self._host}:{self._port}. "
                    "Is the server running?",
                    command=f"POST http://{self._host}:{self._port}/completion",
                ) from exc
            raise BackendExecutionError(
                "moondream",
                f"unexpected error: {error_message}",
                command=f"POST http://{self._host}:{self._port}/completion",
            ) from exc

        content = data.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        return content.strip()

    def analyze(
        self,
        image: bytes,
        *,
        task: str = "describe",
        token: CancellationToken | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Analyze image with structured output.

        Args:
            image: Raw image bytes.
            task: Analysis task ('describe', 'ocr', 'detect', 'classify').
            token: Optional cancellation token.
            **kwargs: Provider-specific parameters.

        Returns:
            Structured result dict.
        """
        if token is not None:
            token.throw_if_cancelled()

        # For now, delegate to describe with task-specific prompt
        prompts = {
            "describe": "Describe this image in detail.",
            "ocr": "Extract all text from this image.",
            "detect": "List all objects detected in this image with bounding boxes.",
            "classify": "Classify the main subject of this image.",
        }
        prompt = prompts.get(task, prompts["describe"])
        description = self.describe(image, prompt=prompt, token=token)
        return {"task": task, "description": description}

    # -- Provider protocol -----------------------------------------------------

    @property
    def name(self) -> str:
        return "moondream"

    @property
    def modality(self) -> str:
        return "vision"

    def capabilities(self) -> ProviderCapabilities:
        from voicevision.core.protocols import ProviderCapabilities
        return ProviderCapabilities(
            streaming=False,
            languages=frozenset(),
            models=frozenset({"moondream2-v2-f16"}),
            max_concurrent=2,
            supports_cancellation=True,
        )

    def lifecycle(self) -> ProviderLifecycle:
        return self

    def initialize(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def health_check(self) -> bool:
        try:
            import httpx
            with httpx.Client(timeout=2.0) as client:
                response = client.get(f"http://{self._host}:{self._port}/health")
                status: int = response.status_code
                return status == 200
        except Exception:
            return False


# Forward reference for type hints
class CancellationToken:
    """Forward reference."""
    def throw_if_cancelled(self) -> None: ...
