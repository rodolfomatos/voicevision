"""Tests for voicevision.listen — microphone → VAD → STT → text on stdout.

No real microphone, no sounddevice, no webrtcvad, and no whisper.cpp binary
are needed: everything is mocked or replaced with the fake child.
"""

from __future__ import annotations

import pytest

# -- main entry point --------------------------------------------------------


class TestMain:
    def test_missing_stt_model_raises_value_error(self) -> None:
        from voicevision.listen import main

        with pytest.raises(ValueError, match="stt_model is required"):
            main()

    def test_main_requires_stt_model(self) -> None:
        from voicevision.listen import main

        with pytest.raises(ValueError, match="stt_model is required"):
            main()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
