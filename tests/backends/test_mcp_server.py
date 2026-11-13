"""Tests for voicevision MCP server using mocks.

No real whisper.cpp, llama.cpp or piper needed — everything is mocked.
"""

from __future__ import annotations

import base64
import io
import json
import sys
from typing import Any

import pytest

from voicevision.backends.mcp_server import MCPServer
from voicevision.server import ServerConfig


def _make_config() -> Any:

    return ServerConfig(
        host="127.0.0.1",
        port=0,
        quiet=True,
        stt_model="/models/whisper-base.bin",
        stt_language="en",
        llm_model="/models/Qwen3-1.7B-Q8_0.gguf",
        llm_host="127.0.0.1",
        llm_port=8080,
        llm_max_tokens=512,
        vision_model="/models/moondream2-text-model-f16.gguf",
        vision_host="127.0.0.1",
        vision_port=8081,
        vision_backend="llama-cpp",
        emotion_enabled=False,
        speaker_enabled=False,
    )


class _FakeService:
    """Fake service that mimics VoiceVisionService methods used by MCP."""

    def __init__(self) -> None:
        self.transcribed: list[tuple[bytes, str]] = []
        self.described: list[tuple[bytes, str]] = []
        self.conversed: list[tuple[str, int]] = []
        self.synthesized: list[str] = []
        self.transcribe_error: Exception | None = None
        self.describe_error: Exception | None = None
        self.converse_error: Exception | None = None
        self.synthesize_error: Exception | None = None

    def transcribe(self, wav: bytes, language: str) -> tuple[str, float]:
        if self.transcribe_error is not None:
            raise self.transcribe_error
        self.transcribed.append((wav, language))
        return "hello world", 12.5

    def describe(self, image: bytes, question: str) -> str:
        if self.describe_error is not None:
            raise self.describe_error
        self.described.append((image, question))
        return "a red bicycle"

    def converse(self, text: str, max_tokens: int) -> str:
        if self.converse_error is not None:
            raise self.converse_error
        self.conversed.append((text, max_tokens))
        return "the answer"

    def synthesize(self, text: str) -> bytes:
        if self.synthesize_error is not None:
            raise self.synthesize_error
        self.synthesized.append(text)
        return b"fake-wav-bytes"


class TestMCPServer:
    """Tests for MCP server using mocks."""

    def _make_server(self) -> tuple[MCPServer, _FakeService]:
        config = _make_config()
        service = _FakeService()
        server = MCPServer(config, service=service)
        return server, service

    def _call_tool(
        self,
        server: MCPServer,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Call a tool method directly (simulating MCP tools/call)."""
        method_name = f"_{name}"
        method = getattr(server, method_name)
        return method(**arguments)

    # -- Construction -------------------------------------------------------

    def test_constructs_with_config(self) -> None:
        config = _make_config()
        server = MCPServer(config)
        assert server.config is config
        assert server.service is not None

    def test_constructs_with_custom_service(self) -> None:
        config = _make_config()
        service = _FakeService()
        server = MCPServer(config, service=service)
        assert server.service is service

    def test_available_tools(self) -> None:
        server, _ = self._make_server()
        tools = server._tools
        assert set(tools.keys()) == {
            "transcribe_audio",
            "describe_image",
            "converse_text",
            "health_check",
        }

    # -- Transcribe ---------------------------------------------------------

    def test_transcribe_audio(self) -> None:
        server, service = self._make_server()
        audio = b"\x00" * 32000
        result = server._transcribe_audio(base64.b64encode(audio).decode(), language="pt")
        assert result["transcript"] == "hello world"
        assert result["language"] == "pt"
        assert result["transcription_ms"] == 12.5
        assert service.transcribed[0][1] == "pt"

    def test_transcribe_audio_error(self) -> None:
        server, service = self._make_server()
        service.transcribe_error = Exception("backend down")
        audio = b"\x00" * 32000
        with pytest.raises(Exception, match="backend down"):
            server._transcribe_audio(base64.b64encode(audio).decode())

    # -- Describe ----------------------------------------------------------

    def test_describe_image(self) -> None:
        server, service = self._make_server()
        result = server._describe_image(
            base64.b64encode(b"fake-image").decode(),
            question="What is this?",
        )
        assert result["description"] == "a red bicycle"
        assert service.described[0][1] == "What is this?"

    def test_describe_image_error(self) -> None:
        server, service = self._make_server()
        service.describe_error = Exception("vision down")
        import base64

        with pytest.raises(Exception, match="vision down"):
            server._describe_image(base64.b64encode(b"fake-image").decode())

    # -- Converse ----------------------------------------------------------

    def test_converse_text(self) -> None:
        server, service = self._make_server()
        result = server._converse_text("hi", max_tokens=32)
        assert result["response"] == "the answer"
        assert service.conversed == [("hi", 32)]

    def test_converse_text_error(self) -> None:
        server, service = self._make_server()
        service.converse_error = Exception("llm down")
        with pytest.raises(Exception, match="llm down"):
            server._converse_text("hi")

    # -- Synthesize TTS -----------------------------------------------------

    # -- Health check -------------------------------------------------------

    def test_health_check(self) -> None:
        server, _ = self._make_server()
        result = server._health_check()
        assert result["status"] == "ok"
        assert result["version"] == "0.3.0"

    # -- Protocol -----------------------------------------------------------

    def test_handle_transcribe_audio_tool(self) -> None:
        server, service = self._make_server()
        import base64

        audio = b"\x00" * 32000
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "transcribe_audio",
                "arguments": {
                    "audio_base64": base64.b64encode(audio).decode(),
                    "language": "pt",
                },
            },
        }
        # Capture stdout
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            server._handle_request(request)
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue().strip()
        response = json.loads(output)
        assert response["id"] == 1
        assert "result" in response
        content = response["result"]["content"][0]["text"]
        result_data = json.loads(content)
        assert result_data["transcript"] == "hello world"

    def test_handle_transcribe_audio_error(self) -> None:
        server, service = self._make_server()
        service.transcribe_error = Exception("backend down")
        import base64

        audio = b"\x00" * 32000
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "transcribe_audio",
                "arguments": {
                    "audio_base64": base64.b64encode(audio).decode(),
                },
            },
        }
        import io

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            server._handle_request(request)
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue().strip()
        response = json.loads(output)
        assert response["id"] == 2
        assert "error" in response
        assert "backend down" in response["error"]["message"]

    def test_unknown_method(self) -> None:
        server, _ = self._make_server()
        import io

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            server._handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "nonexistent",
                        "arguments": {},
                    },
                },
            )
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue().strip()
        response = json.loads(output)
        assert response["id"] == 3
        assert "error" in response
        assert "not found" in response["error"]["message"]
