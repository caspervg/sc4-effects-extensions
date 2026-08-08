"""Generic wire value wrappers and small fixed-shape structs.

``Raw[T]`` is the wire layer's core contract: the wire type is known, the
raw bytes are retained verbatim, and the decoded value is exposed without
claiming any semantic meaning (see effdir-editor-spec.md, "Typed resource
schema"). Every scalar member in the resource model is a ``Raw[T]`` so an
unknown four-byte value is never silently upgraded to a guessed type.

Invariant: ``raw_bytes`` always encodes ``value`` for ``wire_type``. Reads
populate both from the same slice; edits go through ``Raw.replace`` (or the
``make_*`` constructors) so they can never drift apart. Writers therefore
only ever need to emit ``raw_bytes`` verbatim.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Generic, Optional, TypeVar

from .cursor import ReadCursor, SourceSpan, WriteCursor

T = TypeVar("T")

_PACKERS: dict[str, str] = {
    "u8": "<B",
    "u16": "<H",
    "u32": "<I",
    "f32": "<f",
}


@dataclass(frozen=True)
class Raw(Generic[T]):
    """A decoded wire value paired with its exact source bytes."""

    value: T
    wire_type: str
    raw_bytes: bytes
    source_span: Optional[SourceSpan] = None

    def replace(self, value: T) -> "Raw[T]":
        """Return a new Raw with ``value`` re-encoded for the same wire type.

        The result has no ``source_span``: it no longer corresponds to a
        location in the originally read buffer.
        """

        if self.wire_type.startswith("bitset<"):
            fmt = "<I"
        else:
            fmt = _PACKERS[self.wire_type]
        return Raw(value=value, wire_type=self.wire_type, raw_bytes=struct.pack(fmt, value), source_span=None)


def _read_raw(cursor: ReadCursor, wire_type: str, reader) -> Raw:
    start = cursor.pos
    value = reader(cursor)
    return Raw(value=value, wire_type=wire_type, raw_bytes=cursor.data[start : cursor.pos], source_span=cursor.span_since(start))


def read_u8(cursor: ReadCursor) -> Raw[int]:
    return _read_raw(cursor, "u8", ReadCursor.u8)


def read_u16(cursor: ReadCursor) -> Raw[int]:
    return _read_raw(cursor, "u16", ReadCursor.u16)


def read_u32(cursor: ReadCursor) -> Raw[int]:
    return _read_raw(cursor, "u32", ReadCursor.u32)


def read_f32(cursor: ReadCursor) -> Raw[float]:
    return _read_raw(cursor, "f32", ReadCursor.f32)


def read_bitset(cursor: ReadCursor, bits: int) -> Raw[int]:
    """Read a bitset<N>. All observed widths occupy one u32 on the wire."""

    return _read_raw(cursor, f"bitset<{bits}>", ReadCursor.u32)


def make_raw_u8(value: int) -> Raw[int]:
    return Raw(value, "u8", struct.pack("<B", value))


def make_raw_u16(value: int) -> Raw[int]:
    return Raw(value, "u16", struct.pack("<H", value))


def make_raw_u32(value: int) -> Raw[int]:
    return Raw(value, "u32", struct.pack("<I", value))


def make_raw_f32(value: float) -> Raw[float]:
    return Raw(value, "f32", struct.pack("<f", value))


def make_raw_bitset(value: int, bits: int) -> Raw[int]:
    return Raw(value, f"bitset<{bits}>", struct.pack("<I", value))


def write_raw(writer: WriteCursor, raw: Raw) -> None:
    """Emit a Raw's bytes verbatim; see the module invariant above."""

    writer.raw(raw.raw_bytes)


# --- fixed-shape structs (never wrapped in Raw; every member is f32) ----


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class Bounds2:
    minimum: Vec2
    maximum: Vec2


@dataclass(frozen=True)
class Bounds3:
    minimum: Vec3
    maximum: Vec3


def read_vec2(cursor: ReadCursor) -> Vec2:
    return Vec2(cursor.f32(), cursor.f32())


def write_vec2(writer: WriteCursor, v: Vec2) -> None:
    writer.f32(v.x)
    writer.f32(v.y)


def read_vec3(cursor: ReadCursor) -> Vec3:
    return Vec3(cursor.f32(), cursor.f32(), cursor.f32())


def write_vec3(writer: WriteCursor, v: Vec3) -> None:
    writer.f32(v.x)
    writer.f32(v.y)
    writer.f32(v.z)


def read_bounds2(cursor: ReadCursor) -> Bounds2:
    return Bounds2(read_vec2(cursor), read_vec2(cursor))


def write_bounds2(writer: WriteCursor, b: Bounds2) -> None:
    write_vec2(writer, b.minimum)
    write_vec2(writer, b.maximum)


def read_bounds3(cursor: ReadCursor) -> Bounds3:
    return Bounds3(read_vec3(cursor), read_vec3(cursor))


def write_bounds3(writer: WriteCursor, b: Bounds3) -> None:
    write_vec3(writer, b.minimum)
    write_vec3(writer, b.maximum)
