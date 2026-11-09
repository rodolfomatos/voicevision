"""Minimal RFC 6455 WebSocket codec for the local server.

The project refuses to add a mandatory dependency to the HTTP server (T035),
so this module implements the subset of RFC 6455 that a local, JSON-only
streaming endpoint needs:

- the opening handshake accept key
- masked client frames, unmasked server frames
- text/binary data frames, ping, pong and close
- hard limits on frame size, and no extensions or fragmentation

Deliberate omissions are treated as protocol errors rather than silently
ignored. A client that fragments, sets RSV bits, sends an unmasked frame or
uses an unsupported opcode is told exactly why the connection closes. Being
strict here is cheaper than debugging a half-supported protocol later.

Reference: RFC 6455 §4 (handshake), §5 (framing), §7.4 (close codes).
"""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, Protocol

#: RFC 6455 §1.3 handshake GUID.
GUID: Final = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

#: Largest frame this server accepts. One JSON audio chunk is far smaller;
#: the limit exists so a hostile length field cannot allocate unbounded memory.
MAX_FRAME_BYTES: Final = 1024 * 1024

#: Opcodes (RFC 6455 §5.2).
OPCODE_CONTINUATION: Final = 0x0
OPCODE_TEXT: Final = 0x1
OPCODE_BINARY: Final = 0x2
OPCODE_CLOSE: Final = 0x8
OPCODE_PING: Final = 0x9
OPCODE_PONG: Final = 0xA

#: Close codes (RFC 6455 §7.4.1).
CLOSE_NORMAL: Final = 1000
CLOSE_PROTOCOL_ERROR: Final = 1002
CLOSE_UNSUPPORTED: Final = 1003
CLOSE_INVALID_DATA: Final = 1007
CLOSE_TOO_BIG: Final = 1009


class _Reader(Protocol):
    """The read side of a socket stream (``rfile``)."""

    def read(self, size: int, /) -> bytes: ...


class _Writer(Protocol):
    """The write side of a socket stream (``wfile``)."""

    def write(self, data: bytes, /) -> object: ...

    def flush(self) -> None: ...


class WebSocketError(Exception):
    """Base class for WebSocket failures."""


class WebSocketClosed(WebSocketError):
    """The peer closed the connection in the middle of a frame."""


class WebSocketProtocolError(WebSocketError):
    """The peer violated the subset of RFC 6455 this server supports."""

    def __init__(self, code: int, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


@dataclass(frozen=True)
class Frame:
    """One decoded WebSocket frame."""

    opcode: int
    payload: bytes
    fin: bool


def accept_key(client_key: str) -> str:
    """Return the ``Sec-WebSocket-Accept`` value for *client_key*."""
    digest = hashlib.sha1(  # noqa: S324 - SHA-1 is required by RFC 6455
        client_key.encode("ascii") + GUID.encode("ascii")
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_frame(
    payload: bytes,
    opcode: int = OPCODE_TEXT,
    *,
    mask: bytes | None = None,
) -> bytes:
    """Encode a frame.

    Without *mask* the frame is a server frame (RFC 6455 §5.1: never masked).
    With a 4-byte *mask* the payload is masked, which is what a client must do.
    """
    length = len(payload)
    first = 0x80 | (opcode & 0x0F)
    mask_bit = 0x80 if mask is not None else 0x00
    header = bytearray([first])
    if length < 126:
        header.append(mask_bit | length)
    elif length <= 0xFFFF:
        header.append(mask_bit | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(mask_bit | 127)
        header.extend(struct.pack("!Q", length))
    if mask is None:
        return bytes(header) + payload
    if len(mask) != 4:
        raise ValueError("mask must be exactly 4 bytes")
    header.extend(mask)
    masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes(header) + masked


def encode_masked_frame(
    payload: bytes,
    opcode: int = OPCODE_TEXT,
    *,
    mask: bytes | None = None,
) -> bytes:
    """Encode a client frame. A random mask is generated when none is given."""
    if mask is None:
        import os  # noqa: PLC0415 - only needed by the client path

        mask = os.urandom(4)
    return encode_frame(payload, opcode, mask=mask)


def encode_close(code: int = CLOSE_NORMAL, reason: str = "") -> bytes:
    """Encode a close frame, truncating the reason to the 123-byte limit."""
    reason_bytes = reason.encode("utf-8")[:123]
    return encode_frame(struct.pack("!H", code) + reason_bytes, OPCODE_CLOSE)


def _read_exactly(stream: _Reader, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise WebSocketClosed("connection closed mid-frame")
    return data


def _read_length(stream: _Reader, short_length: int) -> int:
    """Expand the 7/16/64-bit payload length field."""
    if short_length == 126:
        return int(struct.unpack("!H", _read_exactly(stream, 2))[0])
    if short_length == 127:
        length = int(struct.unpack("!Q", _read_exactly(stream, 8))[0])
        if length > 0x7FFF_FFFF_FFFF_FFFF:
            raise WebSocketProtocolError(CLOSE_PROTOCOL_ERROR, "invalid frame length")
        return length
    return short_length


def _validate_frame(
    first: int,
    second: int,
    fin: bool,
    opcode: int,
    length: int,
    max_payload: int,
    require_mask: bool,
) -> None:
    """Reject anything outside the supported subset of RFC 6455."""
    if first & 0x70:
        raise WebSocketProtocolError(CLOSE_PROTOCOL_ERROR, "RSV bits are not supported")
    if opcode >= 0x8:
        if not fin:
            raise WebSocketProtocolError(CLOSE_PROTOCOL_ERROR, "control frames must not fragment")
        if length > 125:
            raise WebSocketProtocolError(CLOSE_PROTOCOL_ERROR, "control frame too large")
    elif not fin:
        raise WebSocketProtocolError(CLOSE_UNSUPPORTED, "fragmentation is not supported")
    masked = bool(second & 0x80)
    if require_mask and not masked:
        raise WebSocketProtocolError(CLOSE_PROTOCOL_ERROR, "client frames must be masked")
    if not require_mask and masked:
        raise WebSocketProtocolError(CLOSE_PROTOCOL_ERROR, "server frames must not be masked")
    if length > max_payload:
        raise WebSocketProtocolError(CLOSE_TOO_BIG, f"frame exceeds {max_payload} bytes")


def read_frame(
    stream: _Reader,
    *,
    max_payload: int = MAX_FRAME_BYTES,
    require_mask: bool = True,
) -> Frame:
    """Read and decode one frame.

    ``require_mask=True`` (the default) reads a client frame, which must be
    masked. Pass ``False`` to read an unmasked server frame.

    Raises:
        WebSocketClosed: the peer closed before a complete frame arrived.
        WebSocketProtocolError: RSV bits, fragmentation, wrong masking, control
            frame rules or the size limit were violated.
    """
    header = _read_exactly(stream, 2)
    first, second = header[0], header[1]

    fin = bool(first & 0x80)
    opcode = first & 0x0F
    length = _read_length(stream, second & 0x7F)
    _validate_frame(first, second, fin, opcode, length, max_payload, require_mask)

    mask = _read_exactly(stream, 4) if second & 0x80 else b""
    payload = _read_exactly(stream, length)
    if mask:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return Frame(opcode=opcode, payload=payload, fin=fin)


class WebSocketConnection:
    """Thin send/receive wrapper around a handler's socket streams.

    The defaults are the server side: read masked client frames, write
    unmasked server frames. A client flips both flags.
    """

    def __init__(
        self,
        rfile: _Reader,
        wfile: _Writer,
        *,
        max_payload: int = MAX_FRAME_BYTES,
        mask_outgoing: bool = False,
        require_mask: bool = True,
    ) -> None:
        self._rfile = rfile
        self._wfile = wfile
        self._max_payload = max_payload
        self._mask_outgoing = mask_outgoing
        self._require_mask = require_mask

    def recv(self) -> Frame:
        return read_frame(
            self._rfile,
            max_payload=self._max_payload,
            require_mask=self._require_mask,
        )

    def send(self, payload: bytes, opcode: int = OPCODE_TEXT) -> None:
        frame = (
            encode_masked_frame(payload, opcode)
            if self._mask_outgoing
            else encode_frame(payload, opcode)
        )
        self._wfile.write(frame)
        self._wfile.flush()

    def send_text(self, text: str) -> None:
        self.send(text.encode("utf-8"), OPCODE_TEXT)

    def send_json(self, message: Mapping[str, Any]) -> None:
        self.send_text(json.dumps(message, ensure_ascii=False))

    def pong(self, payload: bytes) -> None:
        self.send(payload, OPCODE_PONG)

    def close(self, code: int = CLOSE_NORMAL, reason: str = "") -> None:
        """Send a close frame; ignore a peer that has already gone away."""
        try:
            if self._mask_outgoing:
                reason_bytes = reason.encode("utf-8")[:123]
                self._wfile.write(
                    encode_masked_frame(
                        struct.pack("!H", code) + reason_bytes,
                        OPCODE_CLOSE,
                    )
                )
            else:
                self._wfile.write(encode_close(code, reason))
            self._wfile.flush()
        except OSError:
            pass
