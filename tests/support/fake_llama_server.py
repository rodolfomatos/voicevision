#!/usr/bin/env python3
"""Stand-in for `llama-server`.

Serves `/health` and `/completion` so the supervision, readiness and transport
paths can be tested against a real subprocess and real HTTP without a model.

Modes:
  --model PATH         recorded, never opened
  --host H --port P    where to listen
  --ready              serve normally (default)
  --never-ready        never return 200 from /health, to test the readiness
                       timeout
  --exit-on-start      exit non-zero immediately, to test startup failure
  --delay SECONDS      stall /health by this long, to test slow startup
  --thinking           include a reasoning trace in responses
  --garbage            return non-JSON, to test response validation
  --http-error         return HTTP 500, to test error surfacing
  --echo-prompt        return the received prompt, to assert request contents
  --log MESSAGE        write MESSAGE to stderr at startup

Mirrors the subset of llama-server's flags that the backend passes, so the
argument construction is exercised rather than bypassed.
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def parse_args(argv: list[str]) -> dict[str, str | bool]:
    opts: dict[str, str | bool] = {}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if not arg.startswith("-"):
            i += 1
            continue
        if arg == "-m":
            opts["model"] = argv[i + 1]
            i += 2
            continue
        if arg in ("--model", "--host", "--port", "--log", "--delay") and i + 1 < len(argv):
            opts[arg.lstrip("-")] = argv[i + 1]
            i += 2
        else:
            opts[arg.lstrip("-")] = True
            i += 1
    return opts


OPTS = parse_args(sys.argv[1:])


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence access logging; it would drown our own stderr messages."""
        del format, args

    def _respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path != "/health":
            self._respond(404, b'{"error":"not found"}')
            return

        if OPTS.get("exit-on-start"):
            return

        delay = float(OPTS.get("delay") or 0)
        if delay:
            time.sleep(delay)

        if OPTS.get("never-ready"):
            # Alive but never healthy: models the "wedged during load" case.
            self._respond(503, b'{"status":"loading model"}')
            return

        self._respond(200, b'{"status":"ok"}')

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path != "/completion":
            self._respond(404, b'{"error":"not found"}')
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"

        if OPTS.get("http-error"):
            self._respond(500, b'{"error":"model failed to generate"}')
            return

        if OPTS.get("garbage"):
            body = b"this is definitely not json"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        try:
            request = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            request = {}

        content = (
            str(request.get("prompt", "")) if OPTS.get("echo-prompt") else " The answer is 42."
        )
        response: dict[str, object] = {"content": content, "stop": True}

        if OPTS.get("thinking"):
            response["thinking"] = "First I will consider the question carefully.</think>"

        self._respond(200, json.dumps(response).encode())


def main() -> int:
    if OPTS.get("log"):
        sys.stderr.write(f"{OPTS['log']}\n")
        sys.stderr.flush()

    if OPTS.get("exit-on-start"):
        sys.stderr.write("error: failed to load model: unsupported quantisation\n")
        return 1

    host = str(OPTS.get("host") or "127.0.0.1")
    port = int(OPTS.get("port") or 0)

    server = ThreadingHTTPServer((host, port), Handler)
    sys.stderr.write(f"llama-server listening on {host}:{server.server_port}\n")
    sys.stderr.flush()
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
