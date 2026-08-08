"""The packed EFFDIR string wire codec.

effdir-editor-spec.md's "String contract" describes a 7-bit continuation
length prefix (citing `DecodeStringLength`/`EncodeStringLength`), but that
document itself flags the vtable `+0x3c` string operation as not fully
traced. Empirically, against the real vanilla EFFDIR resource
(EA5118B0-EA5118B1-00000001 in SimCity_1.dat), string length is a plain
4-byte little-endian u32 immediately followed by that many payload bytes
-- confirmed at multiple non-empty occurrences (e.g. a 12-byte
"debriscorefx" string prefixed by bytes `0C 00 00 00`) and consistent with
every subsequent field decoding to clean, sane values only under this
framing. `DecodeStringLength`'s 7-bit scheme is evidently used by a
different call site, not this one. This is `runtime` evidence (a real
game-generated resource), stronger than the doc's `parser`/`inferred`
claim; effdir-editor-spec.md should be corrected upstream.

There is no serialized NUL terminator: the payload is exactly `length`
bytes.

The packed EFFDIR `std::string` overload is not proven to be UTF-8. The
editor policy is therefore: treat the payload as raw bytes and preserve it
exactly when unchanged; offer strict UTF-8 as a display candidate only
when it validates, and label that as a codec choice, not wire evidence.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

from .cursor import CursorError, ReadCursor, SourceSpan, WriteCursor


@dataclass(frozen=True)
class StringFraming:
    length_encoding: str = "u32"
    length_width: Optional[int] = 4
    length_units: str = "bytes"
    length_signedness: str = "unsigned"
    terminator: str = "none"
    version: Optional[str] = None


@dataclass(frozen=True)
class WireString:
    """A length-prefixed EFFDIR string, retaining raw bytes and a display
    decode attempt (see module docstring for the encoding policy)."""

    decoded: Optional[str]
    raw_bytes: bytes
    encoding: str  # "utf8" | "platform_code_page" | "raw_bytes" | "unknown"
    framing: Optional[StringFraming]
    valid: bool
    changed: bool
    source_span: Optional[SourceSpan] = None

    @staticmethod
    def from_text(text: str) -> "WireString":
        """Construct an edited string from UTF-8 display text.

        This is an explicit, opt-in codec choice by the caller (the editor
        UI), not proof that the wire format is UTF-8.
        """

        return WireString(
            decoded=text,
            raw_bytes=text.encode("utf-8"),
            encoding="utf8",
            framing=StringFraming(),
            valid=True,
            changed=True,
        )

    @staticmethod
    def from_raw_bytes(data: bytes) -> "WireString":
        """Construct an edited string from an explicit raw byte payload,
        for callers who select a codec other than UTF-8 or need to write
        bytes that do not decode as text at all."""

        decoded, valid = _try_decode_utf8(data)
        return WireString(
            decoded=decoded,
            raw_bytes=data,
            encoding="utf8" if valid else "raw_bytes",
            framing=StringFraming(),
            valid=valid,
            changed=True,
        )


def _try_decode_utf8(data: bytes) -> tuple[Optional[str], bool]:
    try:
        return data.decode("utf-8"), True
    except UnicodeDecodeError:
        return None, False


def decode_string_length(cursor: ReadCursor) -> int:
    return cursor.u32()


def encode_string_length(n: int) -> bytes:
    if n < 0:
        raise ValueError(f"negative string length {n}")
    return struct.pack("<I", n)


def read_wire_string(cursor: ReadCursor, *, hard_limit: int = 1 << 24) -> WireString:
    start = cursor.pos
    length = decode_string_length(cursor)
    if length > hard_limit:
        raise CursorError(f"implausible string length {length} at offset {start} (hard limit {hard_limit})")
    payload = cursor.take(length)
    decoded, valid = _try_decode_utf8(payload)
    return WireString(
        decoded=decoded,
        raw_bytes=payload,
        encoding="utf8" if valid else "raw_bytes",
        framing=StringFraming(),
        valid=valid,
        changed=False,
        source_span=cursor.span_since(start),
    )


def write_wire_string(writer: WriteCursor, s: WireString) -> None:
    writer.raw(encode_string_length(len(s.raw_bytes)))
    writer.raw(s.raw_bytes)
