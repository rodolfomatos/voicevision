# ADR-003 — Containerised deployment

- **Status:** Accepted (operator decision, 2026-10-09)
- **Context:** operator confirmed the project runs inside Docker
- **Relates to:** ADR-001 (llama.cpp), ADR-002 (subprocess backends)
- **Ticket:** B7

## Context

Deployment is containerised. That is not a packaging detail — it changes four
things about how the software must behave, and three of them bite at shutdown.

## Decision

A multi-stage image per architecture. Models are a mounted volume, never baked
into the image. Audio is passed through from the host with `--device /dev/snd`.
`tini` is PID 1 for signal forwarding and zombie reaping. `llama-server` is
spawned and supervised by our own process, bound to loopback inside the
container.

## The four consequences

### 1. Audio must be handed in explicitly

A container has no sound hardware. The host device node has to be passed
through, and the container user needs access to it:

```
--device /dev/snd
```

ALSA (not PulseAudio) is the transport. PulseAudio requires a socket mount and
a running daemon on the host, which makes the container non-portable. This is a
real constraint on the target: `sounddevice`/PortAudio must be configured for
the ALSA backend, and `aplay -L` inside the container must list the device
before anything else is worth debugging.

### 2. Models are a volume, not an image layer

qwen3-1.7B GGUF plus a whisper model plus a piper voice is several GB. Baking
that in makes every rebuild push that again and leaves no way to swap models
without rebuilding. Mounted at `/models`, paths supplied via the existing
`VOICEVISION_*` environment variables — which means the config surface designed
in T002 is also the container's configuration surface. No new mechanism.

### 3. PID 1 does not receive default signal handling

Python as PID 1 **ignores SIGTERM**. `docker stop` sends SIGTERM, waits ten
seconds, then SIGKILLs. The result is that every graceful shutdown is actually
a ten-second hang followed by a hard kill.

Two mitigations, both required:
- `tini` as PID 1 (`docker run --init`, or the compose `init: true`) to forward
  signals and reap orphans.
- An explicit `SIGTERM` handler in our entrypoint that runs the same close
  path as context-manager exit.

The second is the one that actually matters, because `close()` ordering is what
decides whether `llama-server` is shut down cleanly before the container dies.
A hard-killed container leaves the model process to be reaped by the runtime
rather than by us.

### 4. `llama-server` supervision crosses the container boundary

We manage the server as a child process (operator decision). Inside the
container it binds `127.0.0.1` by default — it is only reachable from our own
process, which is all that is required since we speak to it over loopback.

Exposing it on `0.0.0.0` to reach it from the host for debugging is possible but
is a debugging affordance, not the default: it turns a local HTTP server with
no authentication into a network service. The port stays configurable, and the
entrypoint prints the flag needed to change it rather than enabling it.

## Consequences

**Positive**
- Identical behaviour on a laptop and a Pi; the image is the environment
- `docker compose up` is the whole deployment story
- Model swap is a file copy into a volume
- Architecture portability via `buildx` (`linux/amd64`, `linux/arm64`)

**Negative**
- ARM64 builds compile llama.cpp from source; first build is slow. Mitigated by
  a cached builder stage.
- Audio debugging inside a container is worse than on the host. Mitigated by an
  entrypoint preflight that fails loudly on a missing `/dev/snd`.
- The image is large (three compiled C/C++ runtimes plus Python). Mitigated by
  multi-stage: build toolchain stays in the builder.

## Alternatives rejected

**Ship models inside the image.** Simpler single-artifact deployment, but every
model change is a rebuild and a multi-GB push. Rejected.

**PulseAudio over ALSA.** Better device handling on desktops. Rejected: it
requires a host daemon and a socket mount, so the container no longer runs
standalone on a Pi.

**Supervise `llama-server` from outside the container.** Cleaner process
lifecycle, more moving parts, and it contradicts the operator's decision to
manage it in-process. Rejected.

## Consequences for the ticket order

Designed before T010 so `LlamaCppBackend` is built against these constraints:
readiness polling must respect a container start-up budget, the port is
configurable, and shutdown ordering is part of its acceptance criteria rather
than an afterthought.