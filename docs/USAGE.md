# Guia de Uso — voicevision

Este documento mostra como usar a biblioteca `voicevision` em cenários reais, desde o uso básico até integrações completas com editor, servidor HTTP e interfaces externas.

## Índice

1. [Instalação rápida](#instalação-rápida)
2. [Uso básico da biblioteca (Python)](#uso-básico-da-biblioteca-python)
3. [Listen mode: ditando para qualquer editor](#listen-mode-ditando-para-qualquer-editor)
4. [Servidor HTTP local](#servidor-http-local)
5. [Cliente Python](#cliente-python)
6. [Integrações prontas](#integrações-prontas)
   - Home Assistant
   - VS Code
   - Obsidian
   - Notion
7. [Pipeline completo com pipeline.py](#pipeline-completo-com-pipelinepy)
8. [Exemplo completo: dia a dia de uso](#exemplo-completo-dia-a-dia-de-uso)
9. [Solução de problemas](#solução-de-problemas)

---

## Instalação rápida

```bash
# 1. Clone o repositório
git clone https://github.com/rodolfomatos/voicevision.git
cd voicevision

# 2. Crie um ambiente virtual (recomendado em Ubuntu/Mint com PEP 668)
python3 -m venv .venv
source .venv/bin/activate

# 3. Instale a biblioteca em modo desenvolvimento
pip install -e ".[dev]"

# 4. Instale dependências de sistema (requer sudo)
make install-voice-input

# 5. Baixe os modelos necessários
make download-models MODELS=voice-loop

# 6. Verifique a instalação
voicevision-preflight
```

Os modelos são baixados para `/models/` por padrão. Você pode alterar com a variável de ambiente `VOICEVISION_MODELS_DIR` se preferir outro local.

---

## Uso básico da biblioteca (Python)

A biblioteca `voicevision` é projetada como um "lego brick": você importa os componentes que precisa e monta o seu próprio fluxo.

### Listen mode: apenas transcrição (sem LLM, sem TTS)

Ideal para digitar por voz em qualquer editor:

```python
from voicevision.listen import ListenConfig, run

config = ListenConfig(
    stt_model="/models/whisper-base.bin",
    stt_language="pt",
    json_output=True,
)

# Captura áudio do microfone, transcreve e imprime JSON no stdout
config.run()
```

Saída JSON:

```json
{
  "transcript": "ola como voce esta",
  "timestamp": "2026-11-13T10:30:00",
  "language": "pt",
  "audio_duration_seconds": 3.5,
  "transcription_ms": 850.2
}
```

### Pipeline completo: áudio de entrada, fala de saída

O pipeline completo executa: VAD → STT → LLM → filtro → TTS.

```python
from voicevision.pipeline import PipelineConfig, VoicePipeline

config = PipelineConfig(
    stt_model="/models/whisper-base.bin",
    stt_language="pt",
    llm_model="/models/Qwen3-1.7B-Q8_0.gguf",
    tts_model="/models/voice.onnx",
    vad_aggressiveness=2,
)

pipeline = VoicePipeline(config)

# Áudio de entrada (PCM16 mono 16kHz)
audio_wav = ...  # bytes de áudio capturado do microfone

# Retorna WAV bytes com a resposta sintetizada
resposta_wav = pipeline.process(audio_wav)
```

O pipeline automaticamente:
1. Segmenta o áudio com VAD (WebRTC)
2. Transcreve cada segmento com whisper.cpp
3. Gera resposta com llama.cpp (Qwen3)
2. Remove traces de raciocínio (thinking filter)
3. Sintetiza a resposta com piper TTS

---

## Listen mode: ditando para qualquer editor

O comando `voicevision-listen` captura áudio do microfone e imprime a transcrição no stdout. Ideal para usar com atalhos de teclado.

```bash
# Grava 5 segundos, transcreve e imprime texto
voicevision-listen --seconds 5

# Com wake word "Olá Ambrósio" — só começa a transcrever após ouvir a palavra
voicevision-listen --wake-word "Olá Ambrósio"

# Modo contínuo: fica escutando até Ctrl+C
voicevision-listen --wake-word "Olá Ambrósio" --continuous

# Saída JSON para automação
voicevision-listen --json --seconds 5

# Modo silencioso: suprime mensagens de stderr (apenas transcrição no stdout)
voicevision-listen --json --quiet --seconds 5
```

### Comando `voicevision-listen-and-copy`

Captura áudio, transcreve e copia automaticamente para a área de transferência (clipboard):

```bash
voicevision-listen-and-copy
```

Depois cole com `Ctrl+V` em qualquer editor (VS Code, Obsidian, terminal, etc.).

**Recomendação:** vincule a um atalho de teclado no seu ambiente desktop (ex: F9) para ditado rápido.

---

## Servidor HTTP local

O servidor expõe endpoints JSON para outros processos se comunicarem com o voicevision sem importar a biblioteca Python.

### Iniciando o servidor

```bash
# Padrão: 127.0.0.1:8765 (apenas localhost)
voicevision-server

# Com token de autenticação
VOICEVISION_SERVER_TOKEN=minha-senha-secreta voicevision-server --port 9000

# Expondo na rede local (apenas se souber o que está fazendo)
voicevision-server --host 0.0.0.0 --port 8765 --token change-me
```

### Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/health` | Status do servidor |
| POST | `/transcribe` | Transcreve áudio (WAV base64) |
| POST | `/describe` | Descreve imagem ou responde pergunta |
| POST | `/converse` | Faz pergunta ao LLM |
| GET | `/stream` | WebSocket streaming de áudio |

### Exemplo: transcrever áudio via curl

```bash
base64 -w0 gravação.wav > /tmp/áudio.b64

curl -s http://127.0.0.1:8765/transcribe \
  -H 'Content-Type: application/json' \
  -d "{\"audio_base64\": \"$(cat /tmp/áudio.b64)\", \"language\": \"pt\"}"
```

Resposta:

```json
{
  "transcript": "Olá, como posso ajudar?",
  "language": "pt",
  "detected_language": null,
  "transcription_ms": 850.2
}
```

### Exemplo: fazer uma pergunta ao LLM

```bash
curl -s http://127.0.0.1:8765/converse \
  -H 'Content-Type: application/json' \
  -d '{"text": "Explique o que é inteligência artificial em 2 frases", "max_tokens": 200}'
```

Resposta:

```json
{
  "response": "A inteligência artificial é a capacidade de máquinas executarem tarefas que normalmente exigiriam inteligência humana, como aprendizado e raciocínio. Ela é amplamente usada em assistentes virtuais, recomendação de conteúdo e automação de tarefas."
}
```

---

## Cliente Python

O módulo `voicevision.client` permite usar a API HTTP de qualquer código Python sem instalar dependências externas.

```python
from voicevision.client import VoiceVisionClient

client = VoiceVisionClient("http://127.0.0.1:8765")

# Verificar se o servidor está online
status = client.health()
print(status)  # {"status": "ok", "version": "0.3.0"}

# Transcrever um arquivo WAV
with open("minha_gravação.wav", "rb") as f:
    resultado = client.transcribe(f.read(), language="pt")
print(resultado["transcript"])  # "ola como voce esta"

# Fazer uma pergunta ao LLM
resposta = client.converse("Explique VAD em uma frase")
print(resposta["response"])  # "VAD detecta atividade de fala em sinais de áudio..."

# Streaming de áudio (WebSocket)
for mensagem in cliente.stream([chunk1, chunk2], language="pt"):
    if mensagem["type"] == "token":
        print(mensagem["text"], end="", flush=True)
```

Com autenticação (bearer token):

```python
client = VoiceVisionClient(
    "http://127.0.0.1:8765",
    token="minha-senha-secreta"
)
```

---

## Integrações prontas

O voicevision vem com integrações prontas para ferramentas populares. Cada uma tem seu próprio diretório em `integrations/` com README detalhado.

### Home Assistant

Integração completa como componente custom do Home Assistant.

**Serviços disponíveis:**
- `voicevision.converse` — envia texto para o LLM
- `voicevision.transcribe` — transcreve arquivo WAV
- `voicevision.describe` — descreve imagem ou responde pergunta

**Exemplo de automação:**

```yaml
automation:
  - alias: "responder pergunta por voz"
    trigger:
      - platform: event
        event_type: voicevision_response
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.service == 'converse' }}"
    action:
      - service: tts.speak
        target:
          entity_id: media_player.sala
        data:
          message: "{{ trigger.event.data.response }}"
```

Veja: `integrations/homeassistant/README.md`

### VS Code

Extensão VS Code com três comandos:
- `voicevision: Dictate` — grava microfone e insere transcrição no cursor
- `voicevision: Transcribe Audio File` — transcreve arquivo WAV selecionado
- `voicevision: Ask About Selection` — envia seleção de texto para o LLM e insere resposta

Bind de teclado sugerido:

```json
[
  { "key": "f9", "command": "voicevision.dictate", "when": "editorTextFocus" },
  { "key": "f10", "command": "voicevision.ask", "when": "editorTextFocus && editorHasSelection" }
```

Veja: `integrations/vscode/README.md`

### Obsidian

Plugin para Obsidian (desktop only):
- `voicevision: Transcribe audio file` — transcreve arquivo WAV e insere na nota
- `voicevision: Ask about selection` — envia seleção para o LLM e insere resposta

Configurações: Server URL, Bearer token, Language, Max tokens.

Veja: `integrations/obsidian/README.md`

### Notion

CLI para exportar transcrições para páginas do Notion:

```bash
# Exportar áudio transcrito para uma página
python integrations/notion/voicevision_notion.py \
  --audio gravação.wav \
  --page-id 0123456789abcdef \
  --title "Reunião de trabalho" \
  --language pt

# Exportar texto existente para um database
python integrations/notion/voicevision_notion.py \
  --text-file nota.txt \
  --database-id 0123456789abcdef \
  --title "Nota de reunião" \
  --title-property Nome

# Verificar payload sem enviar (dry-run)
python integrations/notion/voicevision_notion.py \
  --text-file nota.txt \
  --page-id abc \
  --dry-run
```

Requer `NOTION_TOKEN` definida como variável de ambiente.

Veja: `integrations/notion/README.md`

---

## Pipeline completo com VoicePipeline

Para uso programático completo com controle total:

```python
from voicevision.pipeline import PipelineConfig, VoicePipeline

config = PipelineConfig(
    stt_model="/models/whisper-base.bin",
    stt_language="pt",
    llm_model="/models/Qwen3-1.7B-Q8_0.gguf",
    llm_temperature=0.7,
    llm_max_tokens=512,
    tts_model="/models/voice.onnx",
    vad_aggressiveness=2,
    enable_thinking_filter=True,
    emotion_enabled=True,
    speaker_enabled=True,
)

pipeline = VoicePipeline(config)

# Processar áudio
resultado_wav = pipeline.process(áudio_pcm16_bytes)

# Detectar emoção separadamente
from voicevision.backends.emotion import EmotionResult
emo = pipeline.detect_emotion("Estou muito feliz hoje!")
print(f"Emoção: {emo.label} (confiança: {emo.score:.2f})")

# Identificar falante
falante = pipeline.detect_speaker(segmento_áudio)
print(f"Falante: {falante}")  # "Speaker 1"

# Reiniciar contexto da conversa
pipeline.reset_context()

# Usar como context manager (salva histórico automaticamente ao sair)
with VoicePipeline(config) as pipe:
    resultado = pipe.process(áudio)
```

### Configuração via variáveis de ambiente

Todas as configurações podem ser definidas via variáveis de ambiente:

```bash
export VOICEVISION_STT_MODEL=/models/whisper-base.bin
export VOICEVISION_LLM_MODEL=/models/Qwen3-1.7B-Q8_0.gguf
export VOICEVISION_TTS_MODEL=/models/voice.onnx
export VOICEVISION_STT_LANGUAGE=pt
export VOICEVISION_EMOTION=1
export VOICEVISION_SPEAKER=1
export VOICEVISION_MUTE_TTS=0
export VOICEVISION_VAD_AGGRESSIVENESS=2
export VOICEVISION_VAD_SILENCE_MS=500
export VOICEVISION_MAX_RECORD_SECONDS=60
```

Ou carregar de um arquivo `.env`:

```bash
# .env
VOICEVISION_STT_MODEL=/models/whisper-base.bin
VOICEVISION_LLM_MODEL=/models/Qwen3-1.7B-Q8_0.gguf
VOICEVISION_TTS_MODEL=/models/voice.onnx

# Carregar
source .env
```

---

## Exemplo completo: dia a dia de uso

Cenário: você está trabalhando no computador e quer ditar uma mensagem para o OpenCode sem digitar.

### Passo 1: Configurar atalho de teclado

No Linux Mint (Cinnamon):
1. Configurações → Teclado → Atalhos de teclado
2. Adicionar atalho personalizado:
   - Nome: "Voicevision - Dictar"
   - Comando: `voicevision-listen-and-copy`
   - Tecla: `F9`

### Passo 2: Usar no dia a dia

1. Pressione `F9`
2. Fale: "Olá Ambrósio, explique o que é VAD em português"
3. Solte a tecla
4. A transcrição é copiada para a área de transferência
5. Cole com `Ctrl+V` onde quiser

### Passo 3: Automatizar com servidor

Se quiser que outro aplicativo (ex: um script Python) processe a fala automaticamente:

```python
# script.py
from voicevision.client import VoiceVisionClient

client = VoiceVisionClient("http://127.0.0.1:8765")

# Ouvir e transcrever
resultado = client.transcribe(áudio_bytes, language="pt")
texto = resultado["transcript"]

# Enviar para o LLM
resposta = client.converse(texto)
print(resposta["response"])

# Sintetizar resposta (requer servidor com TTS configurado)
# ...
```

---

## Solução de problemas

| Problema | Causa provável | Solução |
|----------|---------------|---------|
| `BackendNotAvailableError: whispercpp` | whisper.cpp não instalado | `make install-voice-input` ou baixe `whisper-base.bin` |
| `BackendNotAvailableError: piper` | piper não instalado | `pip install piper-tts` ou baixe binário |
| `BackendNotAvailableError: llamacpp` | llama-server não rodando | Inicie `llama-server` na porta 8080 |
| `BackendNotAvailableError: onnxruntime` | ONNX Runtime não instalado | `pip install onnxruntime` |
| `ConfigurationError: STT model not set` | `VOICEVISION_STT_MODEL` não definido | Defina variável de ambiente ou passe `stt_model` no `PipelineConfig` |
| Conexão recusada ao servidor | Servidor não rodando | Inicie `voicevision-server` |
| Erro 401 no servidor | Token incorreto | Verifique `VOICEVISION_SERVER_TOKEN` |
| TTS não produz áudio | Modelo piper corrompido | Baixe novamente com `make download-models MODELS=tts` |
| TTS mudo | `--mute` ou `VOICEVISION_MUTE_TTS=1` | Desative o mute |

### Depuração com preflight

```bash
# Verificar ambiente e dependências
voicevision-preflight

# Ou via make
make doctor
```

---

## Próximos passos

- Leia `docs/REQUISITOS.md` para requisitos funcionais e não-funcionais
- Leia `docs/ROADMAP.md` para o plano de desenvolvimento
- Leia `docs/ADR-001-backends-llamacpp.md` para decisão de arquitetura de backends
- Veja `integrations/` para exemplos de integração com outras ferramentas