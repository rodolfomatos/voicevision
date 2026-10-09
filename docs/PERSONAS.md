# Personas

## Primary User: Embedded AI Developer

**Profile:** Software engineer building robots, kiosks, wearables, or edge devices that need voice/vision AI. Works in Python, deploys to Linux SBCs (RPi, Jetson) or Android devices. Values: minimal dependencies, offline operation, clean APIs, testability.

**Goals:**
- Integrate LLM + STT + TTS + vision in < 1 hour
- Swap backends (ollama ↔ llama.cpp) without code changes
- Run same code on dev machine (Ubuntu) and target (RPi/Android)
- Unit test business logic with dummy backends (no model downloads in CI)

**Pain Points:**
- "Every project I rewrite the same boilerplate for whisper/piper/llama.cpp"
- "Code that works on my laptop fails on RPi due to cv2/pyaudio issues"
- "Testing requires downloading 4GB of models — CI takes forever"
- "No clean way to mock the camera for unit tests"

---

## Secondary User: Platform Maintainer

**Profile:** Engineer maintaining the voicevision library itself. Adds new backends, fixes platform quirks, manages releases.

**Goals:**
- Add new backend in < 100 lines (implement Protocol + register)
- Validate cross-platform compatibility in CI
- Keep dependency graph minimal and auditable

**Tools:**
- AES (Ambrósio Engineering System) for all changes
- `make check` for validation (ruff, mypy, pytest, coverage)
- `make test-android` via emulated Termux (future)

---

## Tertiary User: Application Developer (Consumer)

**Profile:** Builds end-user apps using voicevision as a dependency. Doesn't modify voicevision code.

**Goals:**
- `from voicevision import VoiceVision; vv = VoiceVision(); vv.speak("hello")` — just works
- Configure via `.env` or `VoiceVisionConfig(...)`
- Clear error messages when models missing or hardware unavailable