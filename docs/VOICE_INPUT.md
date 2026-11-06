# Voz → Texto (dictation) no OpenCode

Este documento descreve como configurar um atalho global para falar no microfone e ter o texto transcrito disponível para colar no input do OpenCode, usando o modo `listen` do voicevision.

## Visão geral

O OpenCode **não permite** keybinds que executem comandos shell arbitrários (os keybinds em `tui.json` são limitados a ações pré-definidas: navegação, edição de input, colar do clipboard). A solução é, portanto, um **hotkey global do sistema** que:

1. Executa `voicevision-listen` (microfone → whisper.cpp STT → texto no stdout)
2. Copia o texto para o clipboard (`xclip`)
3. No OpenCode, focas o input e colas com `ctrl+v`

O áudio **não sai da máquina local** — respeita o non-goal de rede do `CLAUDE.md`.

---

## Pré-requisitos

### 1. Pacote voicevision instalado (já feito)

```bash
pip install -e .          # ou: uv sync
```

Isso instala o entry point `voicevision-listen` no PATH.

### 2. whisper.cpp + modelo STT

O `voicevision-listen` depende do binário `whisper-cli` (ou `main`) e de um ficheiro de modelo (ex: `whisper-base.bin`). Estes **não** vêm com o pacote Python — tens de instalá-los à parte.

```bash
# Verificar se o binário existe
which whisper-cli  # ou: which main

# Se não existir, construir whisper.cpp:
#   git clone https://github.com/gggerganov/whisper.cpp
#   cd whisper.cpp && cmake -B build -DCMAKE_BUILD_TYPE=Release
#   cmake --build build --target whisper-cli
# E adicionar build/bin ao PATH

# Baixar um modelo (ex: base) para /models
mkdir -p /models
# whisper-base.bin → /models/whisper-base.bin
```

Definir as variáveis de ambiente no teu `~/.bashrc` (ou `~/.zshrc`):

```bash
export VOICEVISION_STT_MODEL="/models/whisper-base.bin"
export VOICEVISION_STT_LANGUAGE="pt"   # ou "en"
```

Depois: `source ~/.bashrc`

### 3. xclip (clipboard no X11)

```bash
sudo apt-get install xclip
```

> Nota: neste ambiente de desenvolvimento não tive privilégios de sudo para instalar o `xclip`. Instala quando tiveres acesso.

### 4. Microfone / áudio

O `sounddevice` (extra `audio` do voicevision) precisa da biblioteca nativa PortAudio. Em ambiente de desktop Linux normalmente já está presente. Em container, passa o dispositivo de áudio:

```bash
docker run --device /dev/snd ...
```

---

## Instalação do script wrapper

O script já está em:

```
~/.local/bin/voicevision-listen-and-copy
```

Conteúdo:

```sh
#!/bin/sh
set -eu
TEXT=$(voicevision-listen 2>/dev/null || true)
if [ -z "$TEXT" ]; then
    notify-send "voicevision" "Nenhuma fala detetada" 2>/dev/null || true
    exit 0
fi
echo -n "$TEXT" | xclip -selection clipboard
notify-send "voicevision" "Transcrito: $TEXT" 2>/dev/null || true
```

Garantir que é executável:

```bash
chmod +x ~/.local/bin/voicevision-listen-and-copy
```

---

## Configurar o hotkey global (Cinnamon)

1. Abre **Menu → Preferências → Teclado → Atalhos** (Keyboard → Shortcuts)
2. Secção **Personalizados** (Custom shortcuts)
3. Clica em **"+" / Adicionar atalho personalizado**
4. Preenche:
   - **Nome:** `Voz → Texto (OpenCode)`
   - **Comando:** `/home/rodolfo/.local/bin/voicevision-listen-and-copy`
   - **Atalho:** ex: `F9`, `ctrl+alt+v`, ou `super+v` (escolhe algo que não conflite)
5. Guarda

---

## Fluxo de uso

1. Abre o OpenCode e focas o input do chat
2. Pressionas o teu hotkey global (ex: `F9`)
3. Falas claramente — o whisper.cpp transcreve
4. Uma notificação desktop mostra o texto transcrito
5. O texto fica no clipboard
6. No input do OpenCode, pressionas `ctrl+v` para colar
7. Revisas o texto (o agente vai agir com base nele)
8. Pressionas `Enter` para enviar

---

## Testar sem o hotkey

```bash
voicevision-listen-and-copy
# depois, num terminal qualquer:
xclip -selection clipboard -o
```

Se ouvir a notificação e o texto estiver no clipboard, está a funcionar.

---

## Limitações conhecidas

| Item | Detalhe |
|------|---------|
| Latência | whisper.cpp demora segundos por utterance — não é tempo real fluido |
| Sem injeção direta | O texto vai para o clipboard; não é injetado automaticamente no input do OpenCode (limitação do OpenCode) |
| Microfone ausente | Se o OpenCode correr num container sem `/dev/snd`, falha com erro claro |
| Modelo STT | Precisa de `whisper-cli` + ficheiro de modelo configurado via `VOICEVISION_STT_MODEL` |
| xclip | Necessário no X11; em Wayland usa `wl-copy` em vez de `xclip` |

---

## Ficheiros do projeto relacionados

| Ficheiro | Função |
|----------|--------|
| `src/voicevision/listen.py` | Modo listen-only: microfone → VAD → STT → stdout |
| `tests/test_listen.py` | 17 testes de unidade (fakes: sem microfone/whisper real) |
| `pyproject.toml` | Entry point `voicevision-listen = "voicevision.listen:main"` |
| `aes/tickets/T013-listen-mode.md` | Ticket do trabalho concluído |
