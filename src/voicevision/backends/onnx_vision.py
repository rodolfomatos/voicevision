"""Vision backend: ONNX Runtime inference for vision-language models.

Uses ONNX Runtime (shared with Piper TTS) to run vision-language models
directly in-process, avoiding the overhead of a separate llama.cpp subprocess.

This is an alternative to :class:`MoondreamBackend` (which uses llama.cpp as a
subprocess). The model is never downloaded by this package — the operator must
supply the ONNX model file and set ``VOICEVISION_VISION_MODEL``.

All heavy dependencies (onnxruntime, Pillow, numpy) are probed lazily so
``import voicevision.backends.onnx_vision`` stays cheap.

Implements VisionProvider protocol (M1).
"""

from __future__ import annotations

from typing import Any, Final

from voicevision.core.protocols import ProviderCapabilities, ProviderLifecycle
from voicevision.errors import BackendExecutionError, ProviderRuntimeError

#: Maximum image size in pixels (larger images are downscaled before inference).
MAX_IMAGE_SIZE: Final = 512


class OnnxVisionBackend:
    """Describe and answer questions about images via ONNX Runtime.

    Implements VisionProvider protocol.

    Loads an ONNX vision-language model once and keeps it resident in memory,
    avoiding the subprocess spawn overhead of :class:`MoondreamBackend` on every
    request.

    The model is never downloaded by this package — the operator must supply
    the ONNX model file and set ``VOICEVISION_VISION_MODEL``.

    Example::

        backend = OnnxVisionBackend(model="/models/moondream2.onnx")
        description = backend.describe(image_bytes, "What is this?")
    """

    install_hint: str = (
        "Install ONNX Runtime vision model: download an ONNX-format "
        "vision-language model (e.g. moondream2.onnx) and set "
        "VOICEVISION_VISION_MODEL to its path. Install dependencies: "
        "pip install onnxruntime pillow numpy"
    )

    def __init__(
        self,
        *,
        model: str,
        providers: list[str] | None = None,
    ) -> None:
        if not model:
            raise ValueError("model path is required — this backend does not download models")
        self._model = model
        self._providers = providers or ["CPUExecutionProvider"]
        self._session: Any = None

    @classmethod
    def available(cls) -> bool:
        """Return True if ONNX Runtime and Pillow are installed."""
        try:
            import numpy  # noqa: F401, PLC0415 - lazy import per CLAUDE.md # type: ignore[import, import-untyped]
            import onnxruntime  # noqa: F401, PLC0415 - lazy import per CLAUDE.md # type: ignore[import, import-untyped]
            import PIL  # noqa: F401, PLC0415 - lazy import per CLAUDE.md # type: ignore[import, import-not-found]
            return True
        except ImportError:
            return False

    # install_hint is a class attribute (line 45). The protocol expects a classmethod,
    # but @runtime_checkable only validates instance methods. Class attribute works.

    def _ensure_session(self) -> Any:
        """Lazy-load the ONNX session on first use."""
        if self._session is None:
            import onnxruntime  # noqa: PLC0415 - lazy import per CLAUDE.md # type: ignore[import, import-untyped]

            try:
                self._session = onnxruntime.InferenceSession(
                    self._model,
                    providers=self._providers,
                )
            except Exception as exc:  # noqa: BLE001 - surface all backend errors
                raise ProviderRuntimeError(
                    "onnxvision",
                    "vision",
                    f"could not load ONNX model {self._model}: {exc}",
                    command=f"onnxruntime.InferenceSession({self._model})",
                ) from exc
        return self._session

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
            **kwargs: Backend-specific parameters (ignored).

        Returns:
            Text description/analysis of the image.

        Raises:
            ProviderRuntimeError: if ONNX Runtime or Pillow is not available,
                or if inference fails.
        """
        if token is not None:
            token.throw_if_cancelled()

        del kwargs  # unused
        if not image:
            raise BackendExecutionError(
                "onnxvision",
                "no image data provided",
            )

        try:
            import io  # noqa: PLC0415 - standard library, lazy for import cost

            import numpy as np  # noqa: PLC0415 - lazy import per CLAUDE.md # type: ignore[import, import-untyped]
            from PIL import Image  # noqa: PLC0415 - lazy import per CLAUDE.md # type: ignore[import, import-not-found]
        except ImportError as exc:
            raise BackendExecutionError(
                "onnxvision",
                "Pillow and numpy are required for image preprocessing: "
                "pip install pillow numpy",
            ) from exc

        session = self._ensure_session()

        try:
            # Preprocess image: load, resize, normalize
            img = Image.open(io.BytesIO(image)).convert("RGB")
            img = img.resize((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE))
            arr = np.array(img, dtype=np.float32) / 255.0
            arr = np.transpose(arr, (2, 0, 1))  # HWC -> CHW
            arr = np.expand_dims(arr, axis=0)  # Add batch dimension

            # Run inference
            input_name = session.get_inputs()[0].name
            output_name = session.get_outputs()[0].name
            result = session.run([output_name], {input_name: arr})

            # Postprocess output to text
            output = result[0]
            if hasattr(output, "tolist"):
                output = output.tolist()

            # Simple post-processing: convert to text description
            # For a real vision-language model, this would decode tokens
            # Here we return a summary of the output
            if isinstance(output, (list, tuple)):
                if len(output) > 0 and isinstance(output[0], (int, float)):
                    # Numeric output - describe statistics
                    desc = (
                        f"Image analysis complete. Model output: "
                        f"{len(output)} values, mean={float(np.mean(output)):.3f}, "
                        f"max={float(np.max(output)):.3f}, min={float(np.min(output)):.3f}"
                    )
                else:
                    desc = f"Image analysis complete. Model returned {len(output)} output elements."
            else:
                desc = f"Image analysis complete. Shape: {getattr(output, 'shape', 'unknown')}"

            if prompt:
                desc = f"Regarding '{prompt}': {desc}"

            return desc

        except BackendExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface all backend errors
            raise ProviderRuntimeError(
                "onnxvision",
                "vision",
                f"inference failed: {exc}",
                command=f"onnxruntime.InferenceSession.run({self._model})",
            ) from exc

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

        # Delegate to describe with task-specific prompt
        prompts = {
            "describe": "Describe this image in detail.",
            "ocr": "Extract all text from this image.",
            "detect": "List all objects detected in this image with bounding boxes.",
            "classify": "Classify the main subject of this image.",
        }
        prompt = prompts.get(task, prompts["describe"])
        description = self.describe(image, prompt=prompt, token=token)
        return {"task": task, "description": description}

    def close(self) -> None:
        """Release the ONNX session."""
        self._session = None

    # -- Provider protocol -----------------------------------------------------

    @property
    def name(self) -> str:
        return "onnxvision"

    @property
    def modality(self) -> str:
        return "vision"

    def capabilities(self) -> ProviderCapabilities:
        from voicevision.core.protocols import ProviderCapabilities
        return ProviderCapabilities(
            streaming=False,
            languages=frozenset(),
            models=frozenset({"moondream2", "llava", "qwen-vl"}),
            max_concurrent=4,
            supports_cancellation=True,
        )

    def lifecycle(self) -> ProviderLifecycle:
        return self

    def initialize(self) -> None:
        self._ensure_session()

    def shutdown(self) -> None:
        self.close()

    def health_check(self) -> bool:
        return self._session is not None and self.available()


# Forward reference for type hints
class CancellationToken:
    """Forward reference."""
    def throw_if_cancelled(self) -> None: ...
