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


class TestSpeakerIntegration:
    """T092 — optional speaker labels are attached to transcriptions."""

    def test_utterance_is_labelled_with_speaker(self, capsys: pytest.CaptureFixture[str]) -> None:
        from voicevision.listen import ListenSession

        class FakeVAD:
            frame_ms = 30
            max_utterance_ms = 30000

            def process_frame(self, data: bytes) -> bool:
                return False

        class FakeSTT:
            def transcribe(self, audio: bytes, **kwargs: object) -> str:
                return "hello world"

        class FakeSpeaker:
            def identify(self, audio: bytes, **kwargs: object) -> str:
                return "Alice"

        session = ListenSession(
            vad=FakeVAD(),  # type: ignore[arg-type]
            stt=FakeSTT(),
            speaker=FakeSpeaker(),  # type: ignore[arg-type]
        )
        session._process_utterance([b"\x00\x00" * 100])
        assert "[Alice] > hello world" in capsys.readouterr().out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
