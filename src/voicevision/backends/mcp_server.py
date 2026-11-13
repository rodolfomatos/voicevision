"""MCP server para voicevision.

Expõe as capacidades do voicevision como ferramentas MCP (Model Context
Protocol), permitindo que agentes de IA usem o voicevision como ferramenta
através de JSON-RPC over stdio.

Ferramentas expostas:
- transcribe_audio: transcreve áudio em base64 para texto
- describe_image: descreve imagem ou responde pergunta
- converse_text: envia texto para o LLM
- health_check: verifica status do servidor

Uso:
    voicevision-mcp
"""

from __future__ import annotations

import base64
import json
import sys
from typing import Any

from voicevision.server import ServerConfig, VoiceVisionService


class MCPServer:
    """Servidor MCP stdio para voicevision."""

    def __init__(
        self,
        config: ServerConfig,
        service: VoiceVisionService | None = None,
    ) -> None:
        self.config = config
        self.service = service or VoiceVisionService(config)

    # -- Protocol -----------------------------------------------------------

    def run(self) -> None:
        """Loop principal do servidor MCP (stdio transport)."""
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    self._send_error(None, -32700, "Parse error")
                    continue
                self._handle_request(request)
            except (EOFError, KeyboardInterrupt):
                break

    def _send_response(self, request_id: Any, result: Any) -> None:
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _send_error(self, request_id: Any, code: int, message: str) -> None:
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _handle_request(self, request: dict[str, Any]) -> None:
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            self._send_response(request_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "voicevision",
                    "version": "0.3.0",
                },
            })
        elif method == "initialized":
            # Notificação de inicialização concluída - não responde
            return
        elif method == "tools/list":
            self._send_response(request_id, {
                "tools": [
                    {
                        "name": "transcribe_audio",
                        "description": "Transcreve áudio em base64 (WAV, 16 kHz mono PCM16) para texto",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "audio_base64": {
                                    "type": "string",
                                    "description": "Áudio em base64 (WAV, 16 kHz mono PCM16)",
                                },
                                "language": {
                                    "type": "string",
                                    "description": "Código do idioma (pt, en, etc.) ou 'auto' para detecção automática",
                                },
                            },
                            "required": ["audio_base64"],
                        },
                    },
                    {
                        "name": "describe_image",
                        "description": "Descreve imagem ou responde pergunta sobre ela",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "image_base64": {
                                    "type": "string",
                                    "description": "Imagem em base64 (JPEG/PNG)",
                                },
                                "question": {
                                    "type": "string",
                                    "description": "Pergunta sobre a imagem",
                                },
                            },
                            "required": ["image_base64"],
                        },
                    },
                    {
                        "name": "converse_text",
                        "description": "Envia texto para o LLM",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "Texto para enviar ao LLM",
                                },
                                "max_tokens": {
                                    "type": "integer",
                                    "description": "Número máximo de tokens",
                                    "default": 512,
                                },
                            },
                            "required": ["text"],
                        },
                    },
                    {
                        "name": "health_check",
                        "description": "Verifica status do servidor voicevision",
                        "inputSchema": {
                            "type": "object",
                            "properties": {},
                        },
                    },
                ],
            })
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if name in self._tools:
                try:
                    result = self._tools[name](**arguments)
                    self._send_response(request_id, {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                    })
                except Exception as exc:
                    self._send_error(request_id, -32603, f"Internal error: {exc}")
            else:
                self._send_error(request_id, -32601, f"Method not found: {name}")
        else:
            self._send_error(request_id, -32601, f"Method not found: {method}")

    # -- Tool implementations ----------------------------------------------

    def _transcribe_audio(
        self,
        audio_base64: str,
        language: str = "auto",
    ) -> dict[str, Any]:
        """Transcreve áudio em base64 para texto."""
        audio_bytes = base64.b64decode(audio_base64)
        transcript, elapsed_ms = self.service.transcribe(audio_bytes, language)
        return {
            "transcript": transcript,
            "language": language,
            "transcription_ms": round(elapsed_ms, 3),
        }

    def _describe_image(
        self,
        image_base64: str,
        question: str = "",
    ) -> dict[str, Any]:
        """Descreve imagem ou responde pergunta sobre ela."""
        image_bytes = base64.b64decode(image_base64)
        description = self.service.describe(image_bytes, question)
        return {"description": description}

    def _converse_text(
        self,
        text: str,
        max_tokens: int = 512,
    ) -> dict[str, Any]:
        """Envia texto para o LLM."""
        response = self.service.converse(text, max_tokens)
        return {"response": response}

    def _health_check(self) -> dict[str, Any]:
        """Verifica status do servidor."""
        return {"status": "ok", "version": "0.3.0"}

    # -- Tool registry ------------------------------------------------------

    @property
    def _tools(self) -> dict[str, Any]:
        return {
            "transcribe_audio": self._transcribe_audio,
            "describe_image": self._describe_image,
            "converse_text": self._converse_text,
            "health_check": self._health_check,
        }


def main() -> None:
    """Ponto de entrada para voicevision-mcp."""
    from voicevision.server import load_config

    config = load_config()
    server = MCPServer(config)
    server.run()


if __name__ == "__main__":
    main()