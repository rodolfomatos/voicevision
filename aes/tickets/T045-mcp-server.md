---
ticket: T044
title: MCP Server para voicevision
sprint: sprint-04
priority: high
status: in-progress
created: 2026-11-13
---

# T044 — MCP Server para voicevision

## Context

O projeto voicevision já possui uma interface HTTP/WebSocket completa. Para torná-lo acessível a agentes de IA (agentes autônomos, assistentes de código, etc.), deve-se expor as mesmas capacidades via **Model Context Protocol (MCP)**, que é o padrão emergente para expor ferramentas a LLMs.

## Acceptance Criteria

- [ ] `src/voicevision/backends/mcp_server.py` implementado com servidor MCP stdio
- [ ] Ferramentas expostas: `transcribe_audio`, `describe_image`, `converse_text`, `synthesize_tts`, `health_check`
- [ ] `make mcp-server` target no Makefile
- [ ] Testes unitários e de integração para o servidor MCP
- [ ] Documentação em README.md e CHANGELOG.md
- [ ] `make check` verde

## Technical Approach

1. Criar `src/voicevision/backends/mcp_server.py` com servidor MCP stdio
2. Usar protocolo MCP padrão (JSON-RPC over stdio)
3. Expor 5 ferramentas:
   - `transcribe_audio` - transcreve áudio base64
   - `describe_image` - descreve imagem ou responde pergunta
   - `converse_text` - envia texto para o LLM
   - `synthesize_tts` - sintetiza texto para áudio
   - `health_check` - verifica status do servidor
4. Cada ferramenta usa os backends existentes (WhisperCppBackend, MoondreamBackend/OmniVisionBackend, LlamaCppBackend, PiperBackend)
5. Testes com mock dos backends
6. CLI entry point: `voicevision-mcp`

## Out of scope

- WebMCP (versão web) - para versão futura
- Autenticação avançada (bearer token já existe no servidor HTTP)
- Múltiplos servidores simultâneos

## Dependencies

- Depende de todos os backends já implementados (whisper, llama, piper, moondream/onnx)
- Não adiciona dependências externas novas além do que já existe

## Rollback

Remover `src/voicevision/backends/mcp_server.py` e entrada no Makefile

## Rollback

Delete `src/voicevision/backends/mcp_server.py` e remova entrada do Makefile