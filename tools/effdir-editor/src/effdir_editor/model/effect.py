"""cSC4EffectDescription and its child records.

Wire order (effdir.md, "Effect descriptions") is non-monotonic relative to
object member offsets because the two vectors and the string are
non-scalar C++ members; the wire order given here is the *serialization*
order, not ascending `+0xNN`:

    bitset<9>, u32 priority,
    vector<DescriptionRec>, vector<EventRec>,
    string effect_name, u32 start_message_1, u32 start_message_2, u32 start_message_3

`DescriptionRec` embeds a `legacy-transform` (`S3DTransformLegacyLoad` at
0x0009844A: 9 f32 matrix, 3 f32 offset, 1 f32 scale, 1 u32 mode) rather than
an opaque 40-byte blob. effdir.md documents the final field as "1 u8", but
the decompile shows it read via vtable+0x24 (u32) -- only the low byte is
stored into the object (`*param_2 = local_24[0]`), but the wire read
consumes 4 bytes. Treating it as u8 desyncs every DescriptionRec after the
first by 3 bytes.

Version-1 effect descriptions (`ReadVersion1` at 0x003FC72C) stop after
`effect_name` and do not serialize the three start-message scalars; no
`WriteVersion1` has been found, so writing a version-1 resource must not
emit the current three-u32 tail (effdir-editor-spec.md, "Version-1 read
profile"). `read_effect_description`/`write_effect_description` therefore
take the resource's `ReadProfile` explicitly rather than guessing it per
record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from ..wire import (
    Raw,
    ReadCursor,
    RecordPreservation,
    Vec3,
    WireString,
    WireVector,
    WriteCursor,
    make_raw_bitset,
    make_raw_f32,
    make_raw_u8,
    make_raw_u16,
    make_raw_u32,
    read_bitset,
    read_f32,
    read_u8,
    read_u16,
    read_u32,
    read_vec3,
    read_vector,
    read_wire_string,
    write_raw,
    write_vec3,
    write_vector,
    write_wire_string,
)
from .common import ReadProfile


@dataclass
class LegacyTransform:
    """S3DTransformLegacyLoad: 9 f32 (3x3 matrix), 3 f32 (offset), 1 f32
    (scale), 1 u32 (mode; only the low byte is semantically used)."""

    matrix: Tuple[float, float, float, float, float, float, float, float, float]
    offset: Vec3
    scale: float
    mode: Raw[int]


def read_legacy_transform(cursor: ReadCursor) -> LegacyTransform:
    matrix = tuple(cursor.f32() for _ in range(9))
    offset = read_vec3(cursor)
    scale = cursor.f32()
    mode = read_u32(cursor)
    return LegacyTransform(matrix=matrix, offset=offset, scale=scale, mode=mode)


def write_legacy_transform(writer: WriteCursor, t: LegacyTransform) -> None:
    for v in t.matrix:
        writer.f32(v)
    write_vec3(writer, t.offset)
    writer.f32(t.scale)
    write_raw(writer, t.mode)


def default_legacy_transform() -> LegacyTransform:
    """Identity transform. Not a documented constructor default (none is
    given in effdir.md for DescriptionRec); a sane engineering default."""

    return LegacyTransform(
        matrix=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
        offset=Vec3(0.0, 0.0, 0.0),
        scale=1.0,
        mode=make_raw_u32(0),
    )


@dataclass
class DescriptionRecord:
    """DescriptionRec (Read 0x003FC5A4)."""

    name: WireString
    mode: Raw[int]
    flags: Raw[int]  # bitset<2>; bit 0 = ignoreLength/respectLength
    legacy_transform: LegacyTransform
    lod: Raw[int]
    lod_range: Raw[int]
    value_46: Raw[int]
    value_48: Raw[int]
    emit_scale_min: Raw[float]
    emit_scale_max: Raw[float]
    size_scale_min: Raw[float]
    size_scale_max: Raw[float]
    value_5c: Raw[int]
    probability: Raw[int]
    value_60: Raw[int]  # stream vtable +0x20; signedness/type unresolved
    preservation: RecordPreservation = field(default_factory=RecordPreservation)


def read_description_record(cursor: ReadCursor) -> DescriptionRecord:
    return DescriptionRecord(
        name=read_wire_string(cursor),
        mode=read_u8(cursor),
        flags=read_bitset(cursor, 2),
        legacy_transform=read_legacy_transform(cursor),
        lod=read_u8(cursor),
        lod_range=read_u8(cursor),
        value_46=read_u16(cursor),
        value_48=read_u16(cursor),
        emit_scale_min=read_f32(cursor),
        emit_scale_max=read_f32(cursor),
        size_scale_min=read_f32(cursor),
        size_scale_max=read_f32(cursor),
        value_5c=read_u16(cursor),
        probability=read_u16(cursor),
        value_60=read_u32(cursor),
    )


def write_description_record(writer: WriteCursor, d: DescriptionRecord) -> None:
    write_wire_string(writer, d.name)
    write_raw(writer, d.mode)
    write_raw(writer, d.flags)
    write_legacy_transform(writer, d.legacy_transform)
    write_raw(writer, d.lod)
    write_raw(writer, d.lod_range)
    write_raw(writer, d.value_46)
    write_raw(writer, d.value_48)
    write_raw(writer, d.emit_scale_min)
    write_raw(writer, d.emit_scale_max)
    write_raw(writer, d.size_scale_min)
    write_raw(writer, d.size_scale_max)
    write_raw(writer, d.value_5c)
    write_raw(writer, d.probability)
    write_raw(writer, d.value_60)


def default_description_record() -> DescriptionRecord:
    return DescriptionRecord(
        name=WireString(decoded="", raw_bytes=b"", encoding="utf8", framing=None, valid=True, changed=True),
        mode=make_raw_u8(0),
        flags=make_raw_bitset(0, 2),
        legacy_transform=default_legacy_transform(),
        lod=make_raw_u8(1),  # parser default per effdir.md ParseDescRecOptions
        lod_range=make_raw_u8(6),  # parser default
        value_46=make_raw_u16(0),
        value_48=make_raw_u16(0),
        emit_scale_min=make_raw_f32(1.0),
        emit_scale_max=make_raw_f32(1.0),
        size_scale_min=make_raw_f32(1.0),
        size_scale_max=make_raw_f32(1.0),
        value_5c=make_raw_u16(0),
        probability=make_raw_u16(0),
        value_60=make_raw_u32(0),
    )


@dataclass
class EventRecord:
    """EventRec (Read 0x003FC69E): bitset<4>, string, f32, u32."""

    flags: Raw[int]
    name: WireString
    time: Raw[float]
    value: Raw[int]


def read_event_record(cursor: ReadCursor) -> EventRecord:
    return EventRecord(
        flags=read_bitset(cursor, 4),
        name=read_wire_string(cursor),
        time=read_f32(cursor),
        value=read_u32(cursor),
    )


def write_event_record(writer: WriteCursor, e: EventRecord) -> None:
    write_raw(writer, e.flags)
    write_wire_string(writer, e.name)
    write_raw(writer, e.time)
    write_raw(writer, e.value)


def default_event_record() -> EventRecord:
    return EventRecord(
        flags=make_raw_bitset(0, 4),
        name=WireString(decoded="", raw_bytes=b"", encoding="utf8", framing=None, valid=True, changed=True),
        time=make_raw_f32(0.0),
        value=make_raw_u32(0),
    )


@dataclass
class EffectDescription:
    """cSC4EffectDescription (Read 0x003FC790 current / 0x003FC72C version1)."""

    flags: Raw[int]  # bitset<9>: bits 0-8 = viewRelative..manualRestart
    priority: Raw[int]
    descriptions: WireVector[DescriptionRecord]
    events: WireVector[EventRecord]
    effect_name: WireString
    start_message_1: Raw[int]
    start_message_2: Raw[int]
    start_message_3: Raw[int]
    preservation: RecordPreservation = field(default_factory=RecordPreservation)


def read_effect_description(cursor: ReadCursor, profile: ReadProfile) -> EffectDescription:
    flags = read_bitset(cursor, 9)
    priority = read_u32(cursor)
    descriptions = read_vector(cursor, read_description_record)
    events = read_vector(cursor, read_event_record)
    effect_name = read_wire_string(cursor)
    if profile is ReadProfile.VERSION1:
        # ReadVersion1 (0x003FC72C) does not consume these; the executable
        # initializes at least +0x20 to zero in memory.
        start_message_1 = make_raw_u32(0)
        start_message_2 = make_raw_u32(0)
        start_message_3 = make_raw_u32(0)
    else:
        start_message_1 = read_u32(cursor)
        start_message_2 = read_u32(cursor)
        start_message_3 = read_u32(cursor)
    return EffectDescription(
        flags=flags,
        priority=priority,
        descriptions=descriptions,
        events=events,
        effect_name=effect_name,
        start_message_1=start_message_1,
        start_message_2=start_message_2,
        start_message_3=start_message_3,
    )


def write_effect_description(writer: WriteCursor, e: EffectDescription, profile: ReadProfile) -> None:
    write_raw(writer, e.flags)
    write_raw(writer, e.priority)
    write_vector(writer, e.descriptions, write_description_record)
    write_vector(writer, e.events, write_event_record)
    write_wire_string(writer, e.effect_name)
    if profile is ReadProfile.VERSION1:
        # No WriteVersion1 has been identified in the executable; emitting
        # the current 3xu32 tail for a version-1 resource would invent an
        # unverified writer contract (effdir-editor-spec.md, "Writing
        # contract"). Canonical edits to a version-1 resource must be
        # rejected upstream before reaching this function.
        return
    write_raw(writer, e.start_message_1)
    write_raw(writer, e.start_message_2)
    write_raw(writer, e.start_message_3)


def default_effect_description() -> EffectDescription:
    return EffectDescription(
        flags=make_raw_bitset(0, 9),
        priority=make_raw_u32(0),
        descriptions=WireVector(count=0, items=[], source_span=None),
        events=WireVector(count=0, items=[], source_span=None),
        effect_name=WireString(decoded="", raw_bytes=b"", encoding="utf8", framing=None, valid=True, changed=True),
        start_message_1=make_raw_u32(0),
        start_message_2=make_raw_u32(0),
        start_message_3=make_raw_u32(0),
    )
