# voicevision for Home Assistant

A custom component that turns a running [`voicevision-server`](../../../README.md#-local-http-server)
into three Home Assistant services:

| Service | What it does |
|---------|--------------|
| `voicevision.converse` | Send text to the local LLM |
| `voicevision.transcribe` | Transcribe a WAV file with whisper.cpp |
| `voicevision.describe` | Ask the local vision model about an image |

Every result is fired on the event bus as `voicevision_response`, so an
automation decides what to do with it — speak it, notify a phone, write it to a
sensor, or nothing.

Nothing leaves your network: the component talks to the server on
`127.0.0.1:8765` by default.

## Requirements

1. A running `voicevision-server` on the Home Assistant host (or reachable on
   your LAN), with the models configured:

   ```bash
   export VOICEVISION_STT_MODEL=/models/whisper-base.bin
   export VOICEVISION_LLM_MODEL=/models/Qwen3-1.7B-Q8_0.gguf
   export VOICEVISION_VISION_MODEL=/models/moondream2-text-model-f16.gguf
   voicevision-server --host 0.0.0.0 --token change-me
   ```

2. The `voicevision` Python package installed in the same environment as Home
   Assistant:

   ```bash
   # Inside the Home Assistant virtualenv / container
   pip install -e /path/to/voicevision
   ```

   The component imports `voicevision.client`; it does not vendor a copy.

## Install

Copy the `custom_components/voicevision` directory into your Home Assistant
`config/custom_components/` directory and restart Home Assistant:

```bash
cp -r custom_components/voicevision /path/to/homeassistant/config/custom_components/
```

Then add the integration from **Settings → Devices & Services → Add
Integration → voicevision** and enter the base URL (`http://127.0.0.1:8765`)
and, if configured, the bearer token.

## Services

### `voicevision.converse`

```yaml
service: voicevision.converse
data:
  text: "Summarise the state of the house."
  max_tokens: 256
```

Result event:

```yaml
event_type: voicevision_response
data:
  service: converse
  text: "Summarise the state of the house."
  response: "..."
```

### `voicevision.transcribe`

```yaml
service: voicevision.transcribe
data:
  audio_file: "/media/voicevision/note.wav"
  language: "pt"
```

### `voicevision.describe`

```yaml
service: voicevision.describe
data:
  image_file: "/media/voicevision/door.jpg"
  question: "Is there a person at the door?"
```

## Example automation

Speak the answer through any TTS entity:

```yaml
automation:
  - alias: "voicevision answer spoken"
    trigger:
      - platform: event
        event_type: voicevision_response
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.service == 'converse' }}"
    action:
      - service: tts.speak
        target:
          entity_id: tts.piper
        data:
          message: "{{ trigger.event.data.response }}"
          media_player_entity_id: media_player.kitchen
```

## Limitations

- The component is validated structurally in the voicevision test suite; it is
  not exercised against a live Home Assistant instance there.
- `audio_file` / `image_file` must be readable by the Home Assistant process.
- Assist pipeline / wake-word capture inside Home Assistant is out of scope.
