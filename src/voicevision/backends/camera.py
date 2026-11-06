"""Camera backends: OpenCV and Playwright.

Camera backends capture image frames. No model runtime is linked into this
process (ADR-002). OpenCV captures from a local video device; Playwright
captures screenshots from a web page. Both implement the CameraBackend
protocol (core/protocols.py).

All heavy dependencies (opencv-python, playwright) are lazy-imported so
`import voicevision.backends.camera` stays cheap.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import suppress
from typing import Any, ClassVar, Final, cast

from voicevision.errors import BackendExecutionError

#: JPEG quality for OpenCV frame encoding (1-100).
JPEG_QUALITY: Final = 85


class OpenCvCameraBackend:
    """Capture frames from a local video device via OpenCV.

    OpenCV is a heavy dependency; keep it optional via the ``opencv`` extra.
    The import is lazy — it happens only when capture is attempted.
    """

    install_hint: ClassVar[str] = "Install opencv-python: pip install opencv-python-headless"

    def __init__(
        self,
        *,
        index: int = 0,
        resolution: str = "640x480",
        **kwargs: object,
    ) -> None:
        del kwargs  # unused
        self._index = index
        self._resolution = resolution
        self._cap: Any = None

    @classmethod
    def available(cls) -> bool:
        try:
            import cv2  # type: ignore[import-not-found]  # noqa: F401, PLC0415 - lazy import

            return True
        except ImportError:
            return False

    def describe(self) -> str:
        state = "ready" if self.available() else f"unavailable: {self.install_hint}"
        return f"opencv [{state}] index={self._index} resolution={self._resolution}"

    def _open(self) -> Any:
        """Open the camera device. Returns the cv2.VideoCapture object."""
        import cv2  # noqa: PLC0415 - lazy import per CLAUDE.md

        cap: Any = cv2.VideoCapture(self._index)
        if not cap.isOpened():
            cap.release()
            raise BackendExecutionError(
                "opencv",
                f"could not open camera device {self._index}",
                command=f"cv2.VideoCapture({self._index})",
            )
        # Set resolution if provided.
        if self._resolution:
            width, height = self._parse_resolution(self._resolution)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        return cap

    @staticmethod
    def _parse_resolution(resolution: str) -> tuple[int, int]:
        """Parse 'WxH' string into (width, height) tuple."""
        parts = resolution.split("x")
        if len(parts) != 2:
            return (640, 480)
        try:
            return (int(parts[0]), int(parts[1]))
        except ValueError:
            return (640, 480)

    def capture(self, **kwargs: object) -> bytes:
        """Capture a single frame from the camera.

        Returns JPEG-encoded image bytes.
        """
        del kwargs  # unused
        cap = self._open()
        try:
            ret, frame = cap.read()
            if not ret or frame is None:
                raise BackendExecutionError(
                    "opencv",
                    "could not read frame from camera",
                    command=f"cv2.VideoCapture({self._index}).read()",
                )
            import cv2  # noqa: PLC0415 - lazy import per CLAUDE.md

            encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            success, buffer = cv2.imencode(".jpg", frame, encode_params)
            if not success:
                raise BackendExecutionError(
                    "opencv",
                    "could not encode frame as JPEG",
                    command="cv2.imencode(.jpg, frame)",
                )
            return bytes(buffer)
        finally:
            cap.release()

    def capture_stream(self, **kwargs: object) -> Iterator[bytes]:
        """Stream frames from the camera.

        Yields JPEG-encoded image bytes for each frame.
        """
        del kwargs  # unused
        cap = self._open()
        try:
            import cv2  # noqa: PLC0415 - lazy import per CLAUDE.md

            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                success, buffer = cv2.imencode(".jpg", frame, encode_params)
                if not success:
                    continue
                yield bytes(buffer)
        finally:
            cap.release()

    def close(self) -> None:
        """Release the camera device."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class PlaywrightCameraBackend:
    """Capture screenshots from a web page via Playwright.

    Playwright is a heavy dependency; keep it optional via the ``playwright``
    extra. The import is lazy — it happens only when capture is attempted.

    Unlike OpenCV, Playwright does not capture from a physical camera device.
    Instead it navigates to a URL and takes a screenshot. This is useful for
    capturing web content without any camera hardware.
    """

    install_hint: ClassVar[str] = (
        "Install playwright: pip install playwright && playwright install chromium"
    )

    def __init__(
        self,
        *,
        url: str = "about:blank",
        **kwargs: object,
    ) -> None:
        del kwargs  # unused
        self._url = url
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    @classmethod
    def available(cls) -> bool:
        try:
            import playwright  # noqa: F401, PLC0415 - lazy import per CLAUDE.md

            return True
        except ImportError:
            return False

    def describe(self) -> str:
        state = "ready" if self.available() else f"unavailable: {self.install_hint}"
        return f"playwright [{state}] url={self._url}"

    def _start(self) -> None:
        """Start Playwright browser and open a page."""
        from playwright.sync_api import sync_playwright  # noqa: PLC0415 - lazy import

        self._playwright = sync_playwright()
        self._browser = self._playwright.chromium.launch()
        self._page = self._browser.new_page()
        self._page.goto(self._url)

    def capture(self, **kwargs: object) -> bytes:
        """Capture a screenshot of the current page.

        Returns PNG image bytes.
        """
        del kwargs  # unused
        if self._page is None:
            self._start()
        return cast(bytes, self._page.screenshot(full_page=True))

    def capture_stream(self, **kwargs: object) -> Iterator[bytes]:
        """Stream screenshots from the page.

        Yields PNG image bytes for each frame. Reloads the page between frames
        to capture any changes.
        """
        del kwargs  # unused
        if self._page is None:
            self._start()
        while True:
            yield self._page.screenshot(full_page=True)
            self._page.reload(wait_until="domcontentloaded")

    def close(self) -> None:
        """Close the browser and stop Playwright."""
        if self._browser is not None:
            with suppress(Exception):  # noqa: BLE001 - best effort cleanup
                self._browser.close()
            self._browser = None
        if self._playwright is not None:
            with suppress(Exception):  # noqa: BLE001 - best effort cleanup
                self._playwright.stop()
            self._playwright = None
        self._page = None
