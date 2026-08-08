"""The EFFDIR vector wire codec: ``u32 count`` followed by that many
serialized elements, with no element-size or byte-length field
(effdir-editor-spec.md, "Normative wire primitives").

A vector count is validated before allocation. For fixed-size elements,
``element_size`` lets the caller reject an impossible count from the byte
budget alone, before building the list; for variable-size elements,
parsing is bounded element by element by the cursor itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, List, Optional, TypeVar

from .cursor import CursorError, ReadCursor, SourceSpan, WriteCursor

T = TypeVar("T")

DEFAULT_VECTOR_HARD_LIMIT = 1 << 24


@dataclass(frozen=True)
class WireVector(Generic[T]):
    count: int
    items: List[T]
    source_span: Optional[SourceSpan] = None

    def __len__(self) -> int:
        return len(self.items)


def empty_vector() -> WireVector[T]:
    return WireVector(count=0, items=[], source_span=None)


def read_vector(
    cursor: ReadCursor,
    read_element: Callable[[ReadCursor], T],
    *,
    element_size: int | None = None,
    hard_limit: int = DEFAULT_VECTOR_HARD_LIMIT,
) -> WireVector[T]:
    start = cursor.pos
    count = cursor.count(hard_limit=hard_limit)
    if element_size is not None:
        needed = count * element_size
        if needed > cursor.remaining:
            raise CursorError(
                f"vector count {count} at offset {start} needs {needed} bytes, "
                f"only {cursor.remaining} remain"
            )
    items = [read_element(cursor) for _ in range(count)]
    return WireVector(count=count, items=items, source_span=cursor.span_since(start))


def write_vector(
    writer: WriteCursor,
    vec: WireVector[T],
    write_element: Callable[[WriteCursor, T], None],
) -> None:
    # The count is always recomputed from the item list so add/remove
    # operations can never desynchronize it from what is actually written.
    writer.u32(len(vec.items))
    for item in vec.items:
        write_element(writer, item)


@dataclass(frozen=True)
class OptionalVector(Generic[T]):
    """u8 present, optional vector<T>. See effdir.md spine step 16
    (`hasTrailingFloats`)."""

    present: "Raw[int]"  # forward ref to avoid a cycle with types.py
    value: Optional[WireVector[T]]


def read_optional_vector(
    cursor: ReadCursor,
    read_element: Callable[[ReadCursor], T],
    *,
    element_size: int | None = None,
    hard_limit: int = DEFAULT_VECTOR_HARD_LIMIT,
) -> OptionalVector[T]:
    from .types import read_u8

    present = read_u8(cursor)
    value = read_vector(cursor, read_element, element_size=element_size, hard_limit=hard_limit) if present.value != 0 else None
    return OptionalVector(present=present, value=value)


def write_optional_vector(
    writer: WriteCursor,
    vec: OptionalVector[T],
    write_element: Callable[[WriteCursor, T], None],
) -> None:
    from .types import write_raw

    write_raw(writer, vec.present)
    if vec.value is not None:
        write_vector(writer, vec.value, write_element)
