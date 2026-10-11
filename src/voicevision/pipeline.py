"""Voice pipeline: VAD → STT → LLM → filter → TTS.

The main integration point. Wires the backends together into a single
callable that accepts audio bytes and returns synthesized speech bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

from voicevision.backends.piper import PiperBackend
from voicevision.backends.vad import WebrtcVadBackend
from voicevision.backends.whisper_cpp import WhisperCppBackend
from voicevision.backends.llama_cpp import LlamaCppBackend, Completion


@dataclass
class PipelineConfig:
    """Configuration for the voice pipeline."""

    # VAD
    vad_aggressiveness: int = 2
    vad_sample_rate: int = 16000
    vad_silence_ms: int = 500
    vad_max_utterance_ms: int = 30000

    # STT
    stt_model: str = ""
    stt_language: str = "en"

    # LLM
    llm_model: str = ""
    llm_host: str = "127.0.0.1"
    llm_port: int = 8080
    llm_context_size: int = 2048
    llm_gpu_layers: int = 0
    llm_threads: int = 4
    llm_temperature: float = 0.7
    llm_max_tokens: int = 512

    # TTS
    tts_model: str = ""
    tts_voice: str = ""
    tts_length_scale: float = 1.0

    # Filter
    enable_thinking_filter: bool = True


class VoicePipeline:
    """End-to-end voice pipeline: audio in -> audio out."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

        # Lazy-initialized backends
        self._vad = None
        self._stt = None
        self._llm = None
        self._tts = None

    # -- lazy backend accessors ------------------------------------------------

    @property
    def vad(self):
        if self._vad is None:
            self._vad = WebrtcVadBackend(
                aggressiveness=self.config.vad_aggressiveness,
                sample_rate=self.config.vad_sample_rate,
                silence_ms=self.config.vad_silence_ms,
                max_utterance_ms=self.config.vad_max_utterance_ms,
            )
        return self._vad

    @property
    def stt(self):
        if self._stt is None:
            if not self.config.stt_model:
                raise ValueError("stt_model must be configured")
            self._stt = WhisperCppBackend(
                model=self.config.stt_model,
                language=self.config.stt_language,
            )
        return self._stt

    @property
    def llm(self):
        if self._llm is None:
            if not self.config.llm_model:
                raise ValueError("llm_model must be configured")
            self._llm = LlamaCppBackend(
                model=self.config.llm_model,
                host=self.config.llm_host,
                port=self.config.llm_port,
                context_size=self.config.llm_context_size,
                gpu_layers=self.config.llm_gpu_layers,
                threads=self.config.llm_threads,
            )
        return self._llm

    @property
    def tts(self):
        if self._tts is None:
            if not self.config.tts_model:
                raise ValueError("tts_model must be configured")
            self._tts = PiperBackend(
                model=self.config.tts_model,
                voice=self.config.tts_voice,
                length_scale=self.config.tts_length_scale,
            )
        return self._tts

    # -- public API ------------------------------------------------------------

    def process(self, audio: bytes) -> bytes:
        """Process a complete audio stream end-to-end.

        Args:
            audio: PCM16 mono audio at the VAD sample rate.

        Returns:
            Synthesized speech as WAV bytes.
        """
        if not audio:
            return b""

        # 1. VAD: segment audio into utterances
        utterances = list(self.vad.segment(audio))
        if not utterances:
            return b""

        # Process each utterance through the pipeline
        output_chunks = []
        for start, end in utterances:
            utterance_pcm = audio[start:end]

            # 2. STT: transcribe utterance
            transcript = self.stt.transcribe(utterance_pcm)
            if not transcript.strip():
                continue  # Skip empty transcripts

            # 3. LLM: generate response
            completion = self.llm.complete(transcript)
            response_text = completion.content

            # 4. Filter: strip thinking traces if enabled
            if self.config.enable_thinking_filter:
                response_text = self._filter_thinking(response_text)

            if not response_text.strip():
                continue

            # 5. TTS: synthesize response
            speech = self.tts.synthesize(response_text)
            output_chunks.append(speech)

        # Concatenate all speech chunks
        return b"".join(output_chunks)

    def process_stream(self, audio_chunks: Iterator[bytes]) -> Iterator[bytes]:
        """Process a stream of audio chunks, yielding speech as it's ready.

        This is a simplified streaming version that buffers audio until
        VAD detects an utterance, then processes it fully.

        Note: True streaming (token-by-token TTS) is not implemented in v0.1.
        """
        buffer = bytearray()
        for chunk in audio_chunks:
            buffer.extend(chunk)
            # Check if we have a complete utterance
            utterances = list(self.vad.segment(bytes(buffer)))
            if utterances:
                # Process the first utterance
                start, end = utterances[0]
                utterance_pcm = bytes(buffer[start:end])
                # Remove processed audio from buffer
                del buffer[:end]

                transcript = self.stt.transcribe(utterance_pcm)
                if transcript.strip():
                    completion = self.llm.complete(transcript)
                    response = completion.content
                    if self.config.enable_thinking_filter:
                        response = self._filter_thinking(response)
                    if response.strip():
                        yield self.tts.synthesize(response)

        # Process any remaining audio in buffer
        if buffer:
            utterances = list(self.vad.segment(bytes(buffer)))
            for start, end in utterances:
                utterance_pcm = bytes(buffer[start:end])
                transcript = self.stt.transcribe(utterance_pcm)
                if transcript.strip():
                    completion = self.llm.complete(transcript)
                    response = completion.content
                    if self.config.enable_thinking_filter:
                        response = self._filter_thinking(response)
                    if response.strip():
                        yield self.tts.synthesize(response)

    def _filter_thinking(self, text: str) -> str:
        """Strip qwen3 reasoning traces from LLM output.

        qwen3 emits reasoning in several formats:
        - (wrapped in /)
        - (wrapped in special tokens)
        - thinking...prefix (bare prefix before the answer)

        This strips them out before TTS.
        """
        import re

        # Remove  blocks
        text = re.sub(r"thinking.*?response", "", text, flags=re.DOTALL)
        # Remove  blocks
        text = re.sub(r"<\|im_start\|>think.*?<\|im_end\|>", "", text, flags=re.DOTALL)
        # Remove standalone thinking markers
        text = re.sub(r"<\|im_start\|>think", "", text)
        text = re.sub(r"<\|im_end\|>", "", text)
        # Remove bare "thinking..." prefix (qwen3 style)
        text = re.sub(r"^thinking\.\.\.", "", text, flags=re.DOTALL)
        text = re.sub(r"^thinking…", "", text, flags=re.DOTALL)
        return text.strip()

    def close(self) -> None:
        """Release all backend resources."""
        for backend in (self._vad, self._stt, self._llm, self._tts):
            if backend is not None:
                backend.close()

    def __enter__(self) -> VoicePipeline:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()