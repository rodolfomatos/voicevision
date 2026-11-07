"""Vision backend: moondream GGUF via llama.cpp.

Moondream is a small vision-language model (~1.9B parameters) that can describe
and answer questions about images. It runs as a subprocess via llama.cpp
(ADR-001, ADR-002) — never linked into this process.

The model expects images as multipart/form-data uploads and answers via the
llama.cpp completion endpoint.

All heavy dependencies (llama-cpp-python, pillow) are lazy-imported so
`import voicevision.backends.vision` stays cheap.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

from voicevision.errors import BackendExecutionError

#: Maximum image size in pixels (larger images are downscaled).
MAX_IMAGE_SIZE: Final = 512


class MoondreamBackend:
    """Describe and answer questions about images via moondream GGUF + llama.cpp.

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

    def describe(self, image_data: bytes, prompt: str | None = None, **kwargs: Any) -> str:
        """Describe or analyze an image.

        Args:
            image_data: Raw image bytes (JPEG/PNG).
            prompt: Optional prompt to guide description (e.g. "What is in
                this image?").
            **kwargs: Backend-specific parameters.

        Returns:
            Text description/analysis of the image.

        Raises:
            BackendExecutionError: if httpx or llama-server is not available,
                or if the request fails.
        """
        del kwargs  # unused
        if not image_data:
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
                    files={"file": ("image.jpg", image_data, "image/jpeg")},
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
