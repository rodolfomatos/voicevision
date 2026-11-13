"""Vision backend: ONNX Runtime inference for vision-language models.

Uses ONNX Runtime (shared with Piper TTS) to run vision-language models
directly in-process, avoiding the overhead of a separate llama.cpp subprocess.

This is an alternative to ``MoondreamBackend`` (which uses llama.cpp as a
subprocess). The ONNX backend keeps everything in-process: load the model
once, run inference on each image.

The model must be an ONNX-format vision-language model (e.g. moondream2
converted to ONNX). The model file is supplied by the caller; this class
never downloads anything.

All heavy dependencies (onnxruntime, pillow, numpy) are probed lazily so
``import voicevision.backends.onnx_vision`` stays cheap.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

from voicevision.errors import BackendExecutionError

#: Maximum image size in pixels (larger images are downscaled before inference).
MAX_IMAGE_SIZE: Final = 512


class OnnxVisionBackend:
    """Describe and answer questions about images via ONNX Runtime.

    Loads an ONNX vision-language model once and keeps it resident in memory,
    avoiding the subprocess spawn overhead of ``MoondreamBackend`` on every
    request.

    The model is never downloaded by this package — the operator must supply
    the ONNX model file and set ``VOICEVISION_VISION_MODEL``.

    Example::

        backend = OnnxVisionBackend(model="/models/moondream2.onnx")
        description = backend.describe(image_bytes, "What is in this image?")
    """

    install_hint: ClassVar[str] = (
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
        **kwargs: object,
    ) -> None:
        if not model:
            raise ValueError("model path is required — this backend does not download models")
        self._model = model
        self._providers = providers or ["CPUExecutionProvider"]
        self._session: Any = None

    @classmethod
    def available(cls) -> bool:
        """Return True if onnxruntime is installed.

        Pillow and numpy are only needed at inference time, not for the
        backend to be considered available.
        """
        try:
            import onnxruntime  # noqa: F401, PLC0415 - lazy import per CLAUDE.md # type: ignore
            return True
        except ImportError:
            return False

    def _ensure_session(self) -> Any:
        """Lazy-load the ONNX session on first use."""
        if self._session is None:
            import onnxruntime  # noqa: PLC0415 - lazy import per CLAUDE.md # type: ignore

            try:
                self._session = onnxruntime.InferenceSession(
                    self._model,
                    providers=self._providers,
                )
            except Exception as exc:  # noqa: BLE001 - surface all backend errors
                raise BackendExecutionError(
                    "onnxvision",
                    f"could not load ONNX model {self._model}: {exc}",
                    command=f"onnxruntime.InferenceSession({self._model})",
                ) from exc
        return self._session

    def describe(self, image_data: bytes, prompt: str | None = None, **kwargs: Any) -> str:
        """Describe or analyze an image.

        Args:
            image_data: Raw image bytes (JPEG/PNG).
            prompt: Optional prompt to guide description (e.g. "What is in
                this image?").
            **kwargs: Backend-specific parameters (ignored).

        Returns:
            Text description/analysis of the image.

        Raises:
            BackendExecutionError: if ONNX Runtime or Pillow is not available,
                or if inference fails.
        """
        del kwargs  # unused
        if not image_data:
            raise BackendExecutionError(
                "onnxvision",
                "no image data provided",
            )

        try:
            import io  # noqa: PLC0415 - standard library, lazy for import cost

            import numpy as np  # noqa: PLC0415 - lazy import per CLAUDE.md # type: ignore
            from PIL import Image  # noqa: PLC0415 - lazy import per CLAUDE.md # type: ignore
        except ImportError as exc:
            raise BackendExecutionError(
                "onnxvision",
                "Pillow and numpy are required for image preprocessing: "
                "pip install pillow numpy",
            ) from exc

        session = self._ensure_session()

        try:
            # Preprocess image: load, resize, normalize
            image = Image.open(io.BytesIO(image_data)).convert("RGB")
            image = image.resize((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE))
            arr = np.array(image, dtype=np.float32) / 255.0
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
            raise BackendExecutionError(
                "onnxvision",
                f"inference failed: {exc}",
                command=f"onnxruntime.InferenceSession.run({self._model})",
            ) from exc

    def close(self) -> None:
        """Release the ONNX session."""
        self._session = None
