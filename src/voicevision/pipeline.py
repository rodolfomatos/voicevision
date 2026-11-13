"""Voice pipeline: VAD → STT → LLM → filter → TTS.

The main integration point. Wires the backends together into a single
callable that accepts audio bytes and returns synthesized speech bytes.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

from voicevision.backends.emotion import EmotionResult, SimpleEmotionBackend
from voicevision.backends.llama_cpp import LlamaCppBackend
from voicevision.backends.onnx_vision import OnnxVisionBackend
from voicevision.backends.piper import PiperBackend
from voicevision.backends.speaker import SimpleSpeakerBackend
from voicevision.backends.vad import WebrtcVadBackend
from voicevision.backends.vision import MoondreamBackend
from voicevision.backends.whisper_cpp import WhisperCppBackend


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

    # Vision
    vision_backend: str = "llama-cpp"
    vision_model: str = ""
    vision_host: str = "127.0.0.1"
    vision_port: int = 8081

    # Filter
    enable_thinking_filter: bool = True

    # Conversation memory
    max_context_utterances: int = 5
    conversation_path: str = ""
    conversation_ttl_days: int = 30
    max_history_size: int = 100

    # Streaming
    streaming_enabled: bool = False

    # Mute TTS
    mute_tts: bool = False

    # Emotion detection
    emotion_enabled: bool = False

    # Speaker identification
    speaker_enabled: bool = False


class VoicePipeline:
    """End-to-end voice pipeline: audio in -> audio out."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config

        # Lazy-initialized backends
        self._vad: Any = None
        self._stt: Any = None
        self._llm: Any = None
        self._tts: Any = None
        self._vision: Any = None

        # Conversation memory persistence
        self._conversation_path: Path | None = None
        self._conversation_lock = threading.Lock()
        self._conversation_history: list[tuple[str, str]] = []

        if self.config.conversation_path:
            self._conversation_path = Path(self.config.conversation_path).expanduser()
            self.load_context()

    # -- Conversation persistence ----------------------------------------------

    def load_context(self) -> None:
        """Load conversation history from disk.

        Loads JSONL file with format:
        {"timestamp": "2026-11-12T10:30:00Z", "user": "hello", "assistant": "hi"}
        """
        if not self._conversation_path or not self._conversation_path.exists():
            self._conversation_history = []
            return

        with self._conversation_lock:
            history: list[tuple[str, str]] = []
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.config.conversation_ttl_days)

            with self._conversation_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        # Check TTL
                        ts_str = entry.get("timestamp", "")
                        if ts_str:
                            try:
                                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                if ts < cutoff:
                                    continue  # Expired, skip
                            except ValueError:
                                pass
                        user = entry.get("user", "")
                        assistant = entry.get("assistant", "")
                        if user or assistant:
                            history.append((user, assistant))
                    except json.JSONDecodeError:
                        continue

            # Enforce max history size (keep most recent)
            max_size = self.config.max_history_size
            if len(history) > max_size:
                history = history[-max_size:]

            self._conversation_history = history

    def save_context(self) -> None:
        """Save conversation history to disk as JSONL."""
        if not self._conversation_path:
            return

        with self._conversation_lock:
            # Apply size limit before saving (TTL applied on load)
            history = self._conversation_history[-self.config.max_history_size :]

            # Ensure parent directory exists
            self._conversation_path.parent.mkdir(parents=True, exist_ok=True)

            with self._conversation_path.open("w", encoding="utf-8") as f:
                for user_text, assistant_text in history:
                    entry = {
                        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "user": user_text,
                        "assistant": assistant_text,
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # -- lazy backend accessors ------------------------------------------------

    @property
    def vad(self) -> WebrtcVadBackend:
        if self._vad is None:
            self._vad = WebrtcVadBackend(
                aggressiveness=self.config.vad_aggressiveness,
                sample_rate=self.config.vad_sample_rate,
                silence_ms=self.config.vad_silence_ms,
                max_utterance_ms=self.config.vad_max_utterance_ms,
            )
        return cast(WebrtcVadBackend, self._vad)

    @property
    def stt(self) -> WhisperCppBackend:
        if self._stt is None:
            if not self.config.stt_model:
                raise ValueError("stt_model must be configured")
            self._stt = WhisperCppBackend(
                model=self.config.stt_model,
                language=self.config.stt_language,
            )
        return cast(WhisperCppBackend, self._stt)

    @property
    def llm(self) -> LlamaCppBackend:
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
        return cast(LlamaCppBackend, self._llm)

    @property
    def tts(self) -> PiperBackend:
        if self._tts is None:
            if not self.config.tts_model:
                raise ValueError("tts_model must be configured")
            self._tts = PiperBackend(
                model=self.config.tts_model,
                voice=self.config.tts_voice,
                length_scale=self.config.tts_length_scale,
            )
        return cast(PiperBackend, self._tts)

    @property
    def vision(self) -> Any:
        if self._vision is None:
            if not self.config.vision_model:
                raise ValueError("vision_model must be configured")
            if self.config.vision_backend == "onnx":
                self._vision = OnnxVisionBackend(
                    model=self.config.vision_model,
                    providers=["CPUExecutionProvider"],
                )
            else:
                self._vision = MoondreamBackend(
                    model=self.config.vision_model,
                )
        return self._vision

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

        # Reset speaker backend for new session
        if self.config.speaker_enabled:
            SimpleSpeakerBackend().reset()

        # Process each utterance through the pipeline
        output_chunks = []
        for start, end in utterances:
            utterance_pcm = audio[start:end]

            # 2. STT: transcribe utterance
            transcript = self.stt.transcribe(utterance_pcm)
            if not transcript.strip():
                continue  # Skip empty transcripts

            # Speaker identification
            if self.config.speaker_enabled:
                SimpleSpeakerBackend().identify(utterance_pcm)

            # 3. LLM: generate response with conversation context
            context = self._build_conversation_context()
            prompt = f"{context}User: {transcript}\nAssistant:" if context else transcript
            completion = self.llm.complete(prompt)
            response_text = completion.content

            # 4. Filter: strip thinking traces if enabled
            if self.config.enable_thinking_filter:
                response_text = self._filter_thinking(response_text)

            if not response_text.strip():
                continue

            # 5. Store in conversation history
            self._conversation_history.append((transcript, response_text))

            # 6. Emotion detection (if enabled)
            if self.config.emotion_enabled:
                SimpleEmotionBackend().detect(transcript)

            # 7. TTS: synthesize response (unless muted)
            if not self.config.mute_tts:
                output_chunks.append(self.tts.synthesize(response_text))

        # Concatenate all speech chunks
        return b"".join(output_chunks)

    def detect_emotion(self, transcript: str) -> EmotionResult | None:
        """Detect emotion from a transcript if emotion is enabled.

        Args:
            transcript: The transcript text to analyze.

        Returns:
            EmotionResult if emotion detection is enabled, None otherwise.
        """
        if not self.config.emotion_enabled:
            return None
        return SimpleEmotionBackend().detect(transcript)

    def detect_speaker(self, audio: bytes, sample_rate: int = 16000) -> str | None:
        """Identify speaker from audio if speaker identification is enabled.

        Args:
            audio: PCM16 mono audio bytes.
            sample_rate: Sample rate in Hz.

        Returns:
            Speaker label if speaker identification is enabled, None otherwise.
        """
        if not self.config.speaker_enabled:
            return None
        return SimpleSpeakerBackend().identify(audio, sample_rate)

    def process_stream(self, audio_chunks: Iterator[bytes]) -> Iterator[bytes]:
        """Process a stream of audio chunks, yielding speech as it's ready.

        This is a simplified streaming version that buffers audio until
        VAD detects an utterance, then processes it fully.

        When streaming_enabled is True, TTS synthesis starts as soon as the
        LLM generates text chunks, reducing perceived latency.
        """
        buffer = bytearray()
        for chunk in audio_chunks:
            buffer.extend(chunk)
            yield from self._process_buffer(buffer)

        # Process any remaining audio in buffer
        if buffer:
            yield from self._process_buffer(buffer)

    def _process_buffer(self, buffer: bytearray) -> Iterator[bytes]:
        """Process a buffered audio stream, yielding speech for utterances found."""
        utterances = list(self.vad.segment(bytes(buffer)))
        if not utterances:
            return

        # Process the first utterance
        start, end = utterances[0]
        utterance_pcm = bytes(buffer[start:end])
        del buffer[:end]

        transcript = self.stt.transcribe(utterance_pcm)
        if transcript.strip():
            yield from self._process_transcript(transcript)

    def _process_transcript(self, transcript: str) -> Iterator[bytes]:
        """Process a transcript through LLM → filter → TTS.

        When streaming_enabled, yields TTS chunks as soon as the LLM generates
        them. Otherwise, waits for the full response before synthesizing.
        """
        context = self._build_conversation_context()
        prompt = f"{context}User: {transcript}\nAssistant:" if context else transcript

        if self.config.streaming_enabled:
            yield from self._stream_transcript(transcript, prompt)
        else:
            yield from self._process_transcript_sync(transcript, prompt)

    def _stream_transcript(self, transcript: str, prompt: str) -> Iterator[bytes]:
        """Stream transcription: LLM → TTS sentence-by-sentence as they arrive."""
        full_response = ""
        synthesized_until = 0  # Track how much of full_response has been synthesized

        for chunk in self.llm.complete_stream(prompt):
            full_response += chunk
            if not chunk.strip():
                continue

            # Apply thinking filter if enabled
            if self.config.enable_thinking_filter:
                filtered = self._filter_thinking(full_response)
                if not filtered.strip():
                    continue
                text_to_process = filtered
            else:
                text_to_process = full_response

            # Extract complete sentences from the new text
            new_text = text_to_process[synthesized_until:]
            sentences = self._extract_sentences(new_text)

            for sentence in sentences:
                if sentence.strip() and not self.config.mute_tts:
                    yield self.tts.synthesize(sentence)
                synthesized_until += len(sentence)

        # Store in conversation history
        if full_response.strip():
            self._conversation_history.append((transcript, full_response))

    def _process_transcript_sync(self, transcript: str, prompt: str) -> Iterator[bytes]:
        """Process transcript synchronously: wait for full LLM response."""
        completion = self.llm.complete(prompt)
        response_text = completion.content

        # Filter: strip thinking traces if enabled
        if self.config.enable_thinking_filter:
            response_text = self._filter_thinking(response_text)

        if not response_text.strip():
            return

        # Store in conversation history
        self._conversation_history.append((transcript, response_text))

        # TTS: synthesize response (unless muted)
        if not self.config.mute_tts:
            yield self.tts.synthesize(response_text)

    def describe_and_answer(
        self,
        image_data: bytes,
        question: str,
    ) -> bytes:
        """Describe an image and answer a question about it, then synthesize speech.

        Args:
            image_data: Raw image bytes (JPEG/PNG).
            question: Question to ask about the image.

        Returns:
            Synthesized speech as WAV bytes.
        """
        if not image_data:
            return b""

        # 1. Vision: describe the image with the question as context
        description = self.vision.describe(image_data, prompt=question)
        if not description.strip():
            return b""

        # 2. LLM: generate a spoken response to the question based on the description
        if self._llm is not None:
            prompt = (
                f"Based on this image description: '{description}'\n\n"
                f"Question: {question}\n\n"
                f"Answer concisely in a way suitable for text-to-speech:"
            )
            completion = self.llm.complete(prompt)
            response_text = completion.content

            # 3. Filter: strip thinking traces if enabled
            if self.config.enable_thinking_filter:
                response_text = self._filter_thinking(response_text)

            if not response_text.strip():
                return b""

            # 4. TTS: synthesize the response (unless muted)
            if not self.config.mute_tts:
                return self.tts.synthesize(response_text)
            return b""

        # 2b. No LLM configured: return description as text (no TTS)
        return cast(bytes, description.encode("utf-8"))

    def _build_conversation_context(self) -> str:
        """Build conversation context from recent history.

        Returns a formatted string with recent conversation turns,
        limited to max_context_utterances to avoid exceeding context window.
        """
        if not self._conversation_history:
            return ""

        recent = self._conversation_history[-self.config.max_context_utterances :]
        lines = []
        for user_text, assistant_text in recent:
            lines.append(f"User: {user_text}")
            lines.append(f"Assistant: {assistant_text}")
        return "\n".join(lines) + "\n"

    def reset_context(self) -> None:
        """Clear conversation history and saved file."""
        self._conversation_history = []
        if self._conversation_path and self._conversation_path.exists():
            self._conversation_path.unlink(missing_ok=True)

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

    def _extract_sentences(self, text: str) -> list[str]:
        """Extract complete sentences from text using proper boundary detection.

        Handles common edge cases:
        - Abbreviations (Dr., Sr., etc.) - not sentence endings
        - Ellipsis (...) - not sentence endings
        - Quotes and parentheses - handle nesting
        - Multiple punctuation (!?, ...)

        Args:
            text: Input text to split into sentences

        Returns:
            List of complete sentences (stripped, no trailing space)
        """
        if not text.strip():
            return []

        sentences = []
        current = []
        paren_depth = 0
        in_quotes = False
        quote_char = None

        for i, ch in enumerate(text):
            current.append(ch)

            # Track parentheses
            if ch == '(':
                paren_depth += 1
            elif ch == ')':
                paren_depth = max(0, paren_depth - 1)

            # Track quotes
            if ch in ('"', "'", '«', '»', '„', '“', '”'):
                if not in_quotes:
                    in_quotes = True
                    quote_char = ch
                elif ch == quote_char:
                    in_quotes = False
                    quote_char = None

            # Check for sentence endings
            if ch in '.!?':
                # Check for ellipsis
                if i + 2 < len(text) and text[i:i+3] == '...':
                    continue

                # Check for common abbreviations (simple heuristic)
                # Look back for common patterns like "Dr.", "Sr.", "etc."
                if ch == '.':
                    # Look back for abbreviation pattern
                    word_end = i
                    word_start = word_end
                    while word_start > 0 and text[word_start - 1].isalpha():
                        word_start -= 1
                    word = text[word_start:word_end].lower()
                    if word in ('dr', 'sr', 'sra', 'srta', 'prof', 'profª', 'profº',
                                'etc', 'ex', 'p', 'pp', 'cap', 'art', 'inc',
                                'ltd', 'sa', 'eua', 'uk', 'br', 'sp', 'rj'):
                        continue  # Not a sentence end

                # Only split if not inside quotes or parentheses
                if paren_depth == 0 and not in_quotes:
                    sentence = ''.join(current).strip()
                    if sentence:
                        sentences.append(sentence)
                    current = []

        # Handle remaining text (incomplete sentence)
        remaining = ''.join(current).strip()
        if remaining:
            sentences.append(remaining)

        return sentences

    def close(self) -> None:
        """Release all backend resources and save conversation context."""
        self.save_context()
        for backend in (
            self._vad,
            self._stt,
            self._llm,
            self._tts,
            self._vision,
        ):
            if backend is not None:
                backend.close()

    def __enter__(self) -> VoicePipeline:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
