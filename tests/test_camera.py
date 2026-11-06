"""Tests for voicevision.backends.camera.

No real camera, no OpenCV, no Playwright are needed: everything is mocked
or replaced with fakes.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

import voicevision.backends.camera as camera_module

# -- fake modules -------------------------------------------------------------


def _install_fake_cv2(monkeypatch: Any, frames: list[bytes] | None = None) -> None:
    """Inject a fake cv2 module so `import cv2` gets the fake."""
    fake = ModuleType("cv2")

    class FakeVideoCapture:
        def __init__(self, index: int = 0) -> None:
            self._index = index
            self._is_opened = True
            self._released = False

        def isOpened(self) -> bool:
            return self._is_opened and not self._released

        def set(self, prop: int, value: float) -> bool:
            return True

        def read(self) -> tuple[bool, bytes | None]:
            if not self._is_opened or self._released:
                return (False, None)
            frame = frames[0] if frames else b"\x00\x00\x00\x00"
            return (True, frame)

        def release(self) -> None:
            self._released = True

    fake.VideoCapture = FakeVideoCapture
    fake.IMWRITE_JPEG_QUALITY = 1
    fake.imencode = lambda *_: (True, frames[0] if frames else b"\x00\x00")
    fake.CAP_PROP_FRAME_WIDTH = 3
    fake.CAP_PROP_FRAME_HEIGHT = 4

    monkeypatch.setitem(sys.modules, "cv2", fake)


def _install_fake_playwright(monkeypatch: Any, screenshot: bytes = b"\x89PNG") -> None:
    """Inject a fake playwright module so `import playwright` gets the fake."""
    fake_page = MagicMock()
    fake_page.screenshot.return_value = screenshot

    fake_browser = MagicMock()
    fake_browser.new_page.return_value = fake_page

    fake_chromium = MagicMock()
    fake_chromium.launch.return_value = fake_browser

    fake_playwright = MagicMock()
    fake_playwright.chromium = fake_chromium

    fake_sync_api = ModuleType("playwright.sync_api")
    fake_sync_api.sync_playwright = lambda: fake_playwright

    fake = ModuleType("playwright")
    fake.sync_playwright = lambda: fake_playwright
    fake.sync_api = fake_sync_api

    monkeypatch.setitem(sys.modules, "playwright", fake)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", fake_sync_api)


# -- OpenCvCameraBackend ------------------------------------------------------


class TestOpenCvCameraBackend:
    def test_available_false_without_cv2(self, monkeypatch: Any) -> None:
        monkeypatch.setitem(sys.modules, "cv2", None)
        assert camera_module.OpenCvCameraBackend.available() is False

    def test_available_true_with_cv2(self, monkeypatch: Any) -> None:
        _install_fake_cv2(monkeypatch)
        assert camera_module.OpenCvCameraBackend.available() is True

    def test_capture_returns_jpeg_bytes(
        self,
        monkeypatch: Any,
    ) -> None:
        _install_fake_cv2(monkeypatch, frames=[b"\xff\xd8\xff\xe0fake_jpeg"])
        backend = camera_module.OpenCvCameraBackend(index=0, resolution="640x480")
        result = backend.capture()
        assert result == b"\xff\xd8\xff\xe0fake_jpeg"

    def test_describe(self) -> None:
        backend = camera_module.OpenCvCameraBackend(index=0, resolution="640x480")
        desc = backend.describe()
        assert "opencv" in desc
        assert "index=0" in desc
        assert "resolution=640x480" in desc

    def test_install_hint(self) -> None:
        assert "opencv-python" in camera_module.OpenCvCameraBackend.install_hint


class TestOpenCvCameraBackendCaptureStream:
    def test_capture_stream_yields_frames(
        self,
        monkeypatch: Any,
    ) -> None:
        _install_fake_cv2(
            monkeypatch,
            frames=[b"\xff\xd8\xff\xe0frame1", b"\xff\xd8\xff\xe0frame2"],
        )
        backend = camera_module.OpenCvCameraBackend(index=0)
        frames = []
        for i, frame in enumerate(backend.capture_stream()):
            frames.append(frame)
            if i >= 1:
                break
        assert len(frames) == 2


# -- PlaywrightCameraBackend --------------------------------------------------


class TestPlaywrightCameraBackend:
    def test_available_false_without_playwright(self, monkeypatch: Any) -> None:
        monkeypatch.setitem(sys.modules, "playwright", None)
        assert camera_module.PlaywrightCameraBackend.available() is False

    def test_available_true_with_playwright(self, monkeypatch: Any) -> None:
        _install_fake_playwright(monkeypatch)
        assert camera_module.PlaywrightCameraBackend.available() is True

    def test_capture_returns_png_bytes(
        self,
        monkeypatch: Any,
    ) -> None:
        _install_fake_playwright(monkeypatch, screenshot=b"\x89PNGfake")
        backend = camera_module.PlaywrightCameraBackend(url="https://example.com")
        result = backend.capture()
        assert result == b"\x89PNGfake"

    def test_describe(self) -> None:
        backend = camera_module.PlaywrightCameraBackend(url="https://example.com")
        desc = backend.describe()
        assert "playwright" in desc
        assert "https://example.com" in desc

    def test_install_hint(self) -> None:
        assert "playwright" in camera_module.PlaywrightCameraBackend.install_hint

    def test_close_releases_resources(
        self,
        monkeypatch: Any,
    ) -> None:
        _install_fake_playwright(monkeypatch)
        backend = camera_module.PlaywrightCameraBackend()
        backend.capture()
        backend.close()
        # Should not raise on double close
        backend.close()


# -- integration --------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.skipif(
    True,
    reason="requires real camera or playwright browser",
)
def test_real_camera_captures() -> None:
    """Opt-in. Requires a real camera device."""
    backend = camera_module.OpenCvCameraBackend()
    assert backend.available()
    frame = backend.capture()
    assert isinstance(frame, bytes)
    assert len(frame) > 0
