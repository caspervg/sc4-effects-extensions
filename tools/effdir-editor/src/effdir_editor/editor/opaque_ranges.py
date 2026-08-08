"""Byte ranges of an encoded resource that are *not* backed by a decoded
field -- for the hex view's "what don't we understand yet" overlay.

This deliberately does not attempt a full "understood vs. opaque" coverage
map over every byte: fixed-shape structs (Vec2/Vec3/Bounds2/Bounds3) and
vector-of-primitive elements are read directly off the cursor without a
`Raw`/`WireString` wrapper (wire/types.py's module docstring), so they
carry no `source_span`. Treating every span *not* explicitly recorded as
"opaque" would flag large stretches of perfectly understood data (e.g.
every particle's `life: Vec2`) as unknown -- the opposite of the trust
this view is meant to build. Instead this collects only the ranges the
model *positively* marks as preserved-but-uninterpreted:
`PreservationData.trailing_bytes`, `.unknown_top_level`,
`.version_gated_records`, and every record's `RecordPreservation.
unknown_members` (all currently empty for the real vanilla EFFDIR --
effdir.md's format is fully cracked for the versions seen so far -- but
this is live infrastructure for the next file that doesn't round-trip
cleanly, not dead code).
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import List, Tuple

from ..wire import RecordPreservation, WireVector
from ..model.resource import EffDirResource


def opaque_ranges(resource: EffDirResource, encoded_length: int) -> List[Tuple[int, int]]:
    if resource.preservation.original_payload is not None:
        return [(0, len(resource.preservation.original_payload))]

    ranges: List[Tuple[int, int]] = []
    trailing = resource.preservation.trailing_bytes
    if trailing:
        ranges.append((encoded_length - len(trailing), encoded_length))
    for raw_value in (*resource.preservation.unknown_top_level, *resource.preservation.version_gated_records):
        if raw_value.source_span is not None:
            ranges.append((raw_value.source_span.start, raw_value.source_span.end))
    _walk_record_preservation(resource, ranges)
    return ranges


def _walk_record_preservation(value, out: List[Tuple[int, int]]) -> None:
    if isinstance(value, WireVector):
        for item in value.items:
            _walk_record_preservation(item, out)
        return
    if not is_dataclass(value):
        return
    preservation = getattr(value, "preservation", None)
    if isinstance(preservation, RecordPreservation):
        for raw_value in preservation.unknown_members:
            if raw_value.source_span is not None:
                out.append((raw_value.source_span.start, raw_value.source_span.end))
    for f in fields(value):
        _walk_record_preservation(getattr(value, f.name), out)
