# Voz → Texto (dictation) no OpenCode

Este documento descreve como configurar um atalho global para falar no microfone e ter o texto transcrito disponível para colar no input do OpenCode, usando o modo `listen` do voicevision.

## Visão geral

O OpenCode **não permite** keybinds que executem comandos shell arbitrários (os keybinds em `tui.json` são limitados a ações pré-definidas: navegação, edição de input, colar do clipboard). A solução é, portanto, um **hotkey global do sistema** que:

1. Executa `voicevision-listen` (microfone → whisper.cpp STT → texto no stdout)
2. Copia o texto para o clipboard (`xclip`)
3. No OpenCode, focas o input e colas com `ctrl+v`

O áudio **não sai da máquina local** — respeita o non-goal de rede do `CLAUDE.md`.

---

## Instalação integrada (um comando)

Tudo o necessário é instalado com um único comando (requer sudo):

```bash
make install-voice-input
```

O que este comando faz, automaticamente:

1. Instala dependências de sistema: `xclip`, `cmake`, `build-essential`, `git`, `curl`, `python3-pip`
2. Clona whisper.cpp e constrói o binário `whisper-cli` (instalado em `/usr/local/bin`)
3. Baixa o modelo `whisper-base.bin` para `/models/`
4. Instala o pacote Python `voicevision` (`pip install -e .`)
5. Instala o wrapper `~/.local/bin/voicevision-listen-and-copy`
6. Configura `VOICEVISION_STT_MODEL` e `VOICEVISION_STT_LANGUAGE` em `~/.bashrc`

Não são necessários passos manuais adicionais de instalação.

---

## Pré-requisitos de hardware / ambiente

| Item | Detalhe |
|------|---------|
| Microfone | Deve estar acessível na máquina onde o OpenCode corre |
| Áudio (container) | Se o OpenCode correr num container, passe `--device /dev/snd` |
| X11 | O `xclip` funciona em X11. Em Wayland, adapte o wrapper para `wl-copy` |

---

## Configurar o hotkey global (Cinnamon)

1. Abre **Menu → Preferências → Teclado → Atalhos** (Keyboard → Shortcuts)
2. Secção **Personalizados** (Custom shortcuts)
3. Clica em **"+" / Adicionar atalho personalizado**
4. Preenche:
   - **Nome:** `Voz → Texto (OpenCode)`
   - **Comando:** `~/.local/bin/voicevision-listen-and-copy`
   - **Atalho:** ex: `F9`, `ctrl+alt+v`, ou `super+v` (escolha algo que não conflite)
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
source ~/.bashrc
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
| Modelo STT | O `whisper-base.bin` é baixado automaticamente pelo `make install-voice-input` |
| xclip | Necessário no X11; em Wayland, usa `wl-copy` em vez de `xclip` |

---

## Ficheiros do projeto relacionados

| Ficheiro | Função |
|----------|--------|
| `src/voicevision/listen.py` | Modo listen-only: microfone → VAD → STT → stdout |
| `tests/test_listen.py` | 17 testes de unidade (fakes: sem microfone/whisper real) |
| `pyproject.toml` | Entry point `voicevision-listen = "voicevision.listen:main"` |
| `Makefile` | Target `install-voice-input` |
| `install-voice-input.sh` | Instalação completa com sudo (um comando) |
| `scripts/voicevision-listen-and-copy.sh` | Wrapper: grava → transcreve → clipboard |
| `aes/tickets/T013-listen-mode.md` | Ticket do trabalho concluído |
