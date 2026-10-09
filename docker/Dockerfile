# syntax=docker/dockerfile:1.7
#
# voicevision — container image
#
# Multi-stage so the build toolchain for llama.cpp, whisper.cpp and onnxruntime
# does not ship in the runtime image. Models are NOT baked in; they are mounted
# at /models. See docs/ADR-003-container-deployment.md.

ARG BASE_IMAGE=python:3.11-slim-bookworm
ARG TARGETARCH

# --------------------------------------------------------------------------
# Builder: compile the three native runtimes
# --------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS builder

ARG TARGETARCH
ARG LLAMA_BRANCH=b4XXX
ARG WHISPER_REV=v1.7.4

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates pkg-config \
        libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# llama.cpp — provides both llama-server (LLM) and the GGUF runtime (vision)
RUN git clone --depth 1 --branch ${LLAMA_BRANCH} https://github.com/ggml-org/llama.cpp \
    && cmake -S llama.cpp -B llama.cpp/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_NATIVE=OFF \
        -DLLAMA_CURL=ON \
        -DLLAMA_BUILD_TESTS=OFF \
        -DLLAMA_BUILD_EXAMPLES=OFF \
    && cmake --build llama.cpp/build --config Release -j "$(nproc)" --target llama-server llama-cli

# whisper.cpp — speech to text
RUN git clone --depth 1 --branch ${WHISPER_REV} https://github.com/ggerganov/whisper.cpp \
    && cmake -S whisper.cpp -B whisper.cpp/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_NATIVE=OFF \
        -DWHISPER_BUILD_TESTS=OFF \
        -DWHISPER_BUILD_EXAMPLES=OFF \
    && cmake --build whisper.cpp/build --config Release -j "$(nproc)" \
        --target whisper-cli

# --------------------------------------------------------------------------
# Runtime
# --------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS runtime

ARG TARGETARCH

# libsndfile/portaudio for microphone capture and playback (ADR-003 §1)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsndfile1 portaudio19-dev alsa-utils libgomp1 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/llama.cpp/build/bin/llama-server /usr/local/bin/
COPY --from=builder /build/llama.cpp/build/bin/llama-cli    /usr/local/bin/
COPY --from=builder /build/whisper.cpp/build/bin/whisper-cli /usr/local/bin/

# piper is distributed as a prebuilt binary per architecture
ARG PIPER_RELEASE=2023.11.14-2
RUN set -eux; \
    case "${TARGETARCH}" in \
        amd64) piper_pkg="piper_linux_x86_64.tar.gz" ;; \
        arm64) piper_pkg="piper_linux_aarch64.tar.gz" ;; \
        *) echo "unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/piper.tar.gz \
        "https://github.com/rhasspy/piper/releases/download/${PIPER_RELEASE}/${piper_pkg}"; \
    tar -xzf /tmp/piper.tar.gz -C /tmp; \
    install -m 0755 "/tmp/piper/${piper_pkg%.tar.gz}/piper" /usr/local/bin/piper; \
    rm -rf /tmp/piper /tmp/piper.tar.gz

RUN useradd --create-home --shell /bin/bash --uid 1000 voicevision \
    && mkdir -p /models \
    && chown voicevision:voicevision /models

COPY --chown=voicevision:voicevision . /app
RUN pip install --no-cache-dir /app

# Models are mounted here, never baked in (ADR-003 §2)
VOLUME ["/models"]

USER voicevision
WORKDIR /app

ENV VOICEVISION_LLM_MODEL=/models/qwen3-1.7b-q4_k_m.gguf \
    VOICEVISION_STT_MODEL=/models/whisper-base.bin \
    VOICEVISION_TTS_MODEL=/models/piper-en-medium.onnx \
    VOICEVISION_LLM_BACKEND=llamacpp \
    VOICEVISION_STT_BACKEND=whispercpp \
    VOICEVISION_TTS_BACKEND=piper \
    PYTHONUNBUFFERED=1

# Only meaningful if VOICEVISION_LLM_HOST=0.0.0.0; loopback is the default
# (ADR-003 §4) because the server has no authentication.
EXPOSE 8080

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["voicevision-preflight"]