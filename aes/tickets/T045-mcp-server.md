---
ticket: T045
title: MCP Server para voicevision
sprint: sprint-04
priority: high
status: done
created: 2026-11-13
completed: 2026-11-13
---

# T045 — MCP Server para voicevision

## Context

O projeto voicevision já possui uma interface HTTP/WebSocket completa. Para torná-lo acessível a agentes de IA (agentes autônomos, assistentes de código, etc.), deve-se expor as mesmas capacidades via **Model Context Protocol (MCP)**, que é o padrão emergente para expor ferramentas a LLMs.

## Acceptance Criteria

- [x] `src/voicevision/backends/mcp_server.py` implementado com servidor MCP stdio
- [x] Ferramentas expostas: `transcribe_audio`, `describe_image`, `converse_text`, `health_check`
- [ ] `make aes-mcp-server` target no Makefile
- [x] Testes unitários e de integração para o servidor MCP
- [x] Documentação em README.md e CHANGELOG.md
- [x] `make check` verde

## Technical Approach

1. Criar `src/voicevision/backends/mcp_server.py` com servidor MCP stdio
2. Usar protocolo MCP padrão (JSON-RPC over stdio)
3. Expor 4 ferramentas:
   - `transcribe_audio` - transcreve áudio base64
   - `describe_image` - descreve imagem ou responde pergunta
   - `converse_text` - envia texto para o LLM
   - `health_check` - verifica status do servidor
4. Cada ferramenta usa os backends existentes (WhisperCppBackend, MoondreamBackend/OmniVisionBackend, LlamaCppBackend)
5. Testes com mock dos backends
6. CLI entry point: `voicevision-mcp`

## Out of scope

- WebMCP (versão web) - para versão futura
- Autenticação avançada (bearer token já existe no servidor HTTP)
- Múltiplos servidores simultâneos
- `synthesize_tts` - o servidor HTTP não expõe TTS diretamente (está apenas no VoicePipeline)

## Dependencies

- Depende de todos os backends já implementados (whisper, llama, piper, moondream/onnx)
- Não adiciona dependências externas novas além do que já existe

## Rollback

Remover `src/voicevision/backends/mcp_server.py` e remover entrada do Makefile

## Known Risks

- O servidor MCP roda via stdio, não como serviço HTTP separado
- Não há suporte a múltiplos clientes simultâneos (stdio é single-client por natureza)
- O TTS não é exposto via MCP pois o servidor HTTP não expõe essa funcionalidade diretamente (está apenas no VoicePipeline)
