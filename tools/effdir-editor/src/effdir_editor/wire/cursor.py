"""Bounded little-endian cursor over an in-memory byte buffer.

Implements the scalar stream operations recovered from the SC4 executable
(see docs/reference/binary/effdir.md): u8/u16/u32/f32 reads selected by
stream vtable offset. String and vector framing build on top of this in
``strings.py`` and ``vectors.py``.

Every read validates that enough bytes remain before consuming them, per
the parsing contract: "for every count, check the remaining byte budget
before allocation."
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


class CursorError(ValueError):
    """Truncated record, invalid string/vector bound, or impossible count."""


@dataclass(frozen=True)
class SourceSpan:
    """A byte range in a buffer that produced a decoded value."""

    start: int
    end: int

    def __len__(self) -> int:
        return self.end - self.start


class ReadCursor:
    """A bounds-checked reader over a fixed byte buffer."""

    __slots__ = ("data", "pos")

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def __len__(self) -> int:
        return len(self.data)

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    def at_end(self) -> bool:
        return self.pos >= len(self.data)

    def require(self, n: int) -> None:
        if n < 0:
            raise CursorError(f"negative read length {n} at offset {self.pos}")
        if self.remaining < n:
            raise CursorError(
                f"truncated record: need {n} bytes at offset {self.pos}, "
                f"only {self.remaining} remain"
            )

    def take(self, n: int) -> bytes:
        self.require(n)
        start = self.pos
        self.pos += n
        return self.data[start : self.pos]

    def span_since(self, start: int) -> SourceSpan:
        return SourceSpan(start, self.pos)

    def peek(self, n: int) -> bytes:
        self.require(n)
        return self.data[self.pos : self.pos + n]

    # --- primitives ----------------------------------------------------

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack_from("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack_from("<I", self.take(4))[0]

    def f32(self) -> float:
        return struct.unpack_from("<f", self.take(4))[0]

    def count(self, *, hard_limit: int) -> int:
        """Read a raw ``u32`` vector/string-length-style count.

        Rejects implausible counts before the caller allocates or loops,
        per the parsing contract. ``hard_limit`` is an editor safety
        valve, not a claim about an executable-imposed limit.
        """

        start = self.pos
        n = self.u32()
        if n > hard_limit:
            raise CursorError(
                f"implausible count {n} at offset {start} "
                f"(hard limit {hard_limit})"
            )
        return n


class WriteCursor:
    """An append-only little-endian byte builder."""

    __slots__ = ("buffer",)

    def __init__(self) -> None:
        self.buffer = bytearray()

    def __len__(self) -> int:
        return len(self.buffer)

    @property
    def pos(self) -> int:
        return len(self.buffer)

    def raw(self, data: bytes) -> None:
        self.buffer.extend(data)

    def u8(self, value: int) -> None:
        self.buffer.append(value & 0xFF)

    def u16(self, value: int) -> None:
        self.buffer.extend(struct.pack("<H", value))

    def u32(self, value: int) -> None:
        self.buffer.extend(struct.pack("<I", value))

    def f32(self, value: float) -> None:
        self.buffer.extend(struct.pack("<f", value))

    def getvalue(self) -> bytes:
        return bytes(self.buffer)
