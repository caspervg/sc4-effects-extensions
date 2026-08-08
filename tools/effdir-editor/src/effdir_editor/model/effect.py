"""cSC4EffectDescription and its child records.

Wire order (effdir.md, "Effect descriptions") is non-monotonic relative to
object member offsets because the two vectors and the string are
non-scalar C++ members; the wire order given here is the *serialization*
order, not ascending `+0xNN`:

    bitset<9>, u32 priority,
    vector<DescriptionRec>, vector<EventRec>,
    string effect_name, u32 start_message_1, u32 start_message_2, u32 start_message_3

`DescriptionRec` embeds a `legacy-transform` (`S3DTransformLegacyLoad` at
0x0009844A: 3 row-major Vec3 matrix rows, a Vec3 translation, uniform scale,
and a u32 revision word) rather than
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
class Matrix3:
    """Row-major cS3DMatrix3 storage exposed as three editable vectors."""

    row_0: Vec3
    row_1: Vec3
    row_2: Vec3


@dataclass
class LegacyTransform:
    """Legacy cS3DTransform payload without its derived in-memory flag byte."""

    matrix: Matrix3
    translation: Vec3
    scale: float
    revision: Raw[int]  # u32 on wire; cS3DTransform stores/uses the low byte


def read_legacy_transform(cursor: ReadCursor) -> LegacyTransform:
    matrix = Matrix3(read_vec3(cursor), read_vec3(cursor), read_vec3(cursor))
    translation = read_vec3(cursor)
    scale = cursor.f32()
    revision = read_u32(cursor)
    return LegacyTransform(matrix=matrix, translation=translation, scale=scale, revision=revision)


def write_legacy_transform(writer: WriteCursor, t: LegacyTransform) -> None:
    write_vec3(writer, t.matrix.row_0)
    write_vec3(writer, t.matrix.row_1)
    write_vec3(writer, t.matrix.row_2)
    write_vec3(writer, t.translation)
    writer.f32(t.scale)
    write_raw(writer, t.revision)


def default_legacy_transform() -> LegacyTransform:
    """Identity transform matching cS3DTransform's constructor."""

    return LegacyTransform(
        matrix=Matrix3(
            row_0=Vec3(1.0, 0.0, 0.0),
            row_1=Vec3(0.0, 1.0, 0.0),
            row_2=Vec3(0.0, 0.0, 1.0),
        ),
        translation=Vec3(0.0, 0.0, 0.0),
        scale=1.0,
        revision=make_raw_u32(0),
    )


@dataclass
class DescriptionRecord:
    """DescriptionRec (Read 0x003FC5A4)."""

    name: WireString
    component_type: Raw[int]  # +0x04, tSC4ComponentEffectType
    flags: Raw[int]  # bitset<2>: ignoreLength and systemSequence
    legacy_transform: LegacyTransform
    lod: Raw[int]
    lod_range: Raw[int]
    shell_count: Raw[int]  # +0x46, particle "shells" count
    shell_delay: Raw[int]  # +0x48, per-shell delay passed as param 0x101
    emit_scale_min: Raw[float]
    emit_scale_max: Raw[float]
    size_scale_min: Raw[float]
    size_scale_max: Raw[float]
    selection_group: Raw[int]  # +0x5c, enclosing select-group id (0 = none)
    probability: Raw[int]
    description_index: Raw[int]  # +0x60, resolved component-description index; -1 until resolved
    preservation: RecordPreservation = field(default_factory=RecordPreservation)


def read_description_record(cursor: ReadCursor) -> DescriptionRecord:
    return DescriptionRecord(
        name=read_wire_string(cursor),
        component_type=read_u8(cursor),
        flags=read_bitset(cursor, 2),
        legacy_transform=read_legacy_transform(cursor),
        lod=read_u8(cursor),
        lod_range=read_u8(cursor),
        shell_count=read_u16(cursor),
        shell_delay=read_u16(cursor),
        emit_scale_min=read_f32(cursor),
        emit_scale_max=read_f32(cursor),
        size_scale_min=read_f32(cursor),
        size_scale_max=read_f32(cursor),
        selection_group=read_u16(cursor),
        probability=read_u16(cursor),
        description_index=read_u32(cursor),
    )


def write_description_record(writer: WriteCursor, d: DescriptionRecord) -> None:
    write_wire_string(writer, d.name)
    write_raw(writer, d.component_type)
    write_raw(writer, d.flags)
    write_legacy_transform(writer, d.legacy_transform)
    write_raw(writer, d.lod)
    write_raw(writer, d.lod_range)
    write_raw(writer, d.shell_count)
    write_raw(writer, d.shell_delay)
    write_raw(writer, d.emit_scale_min)
    write_raw(writer, d.emit_scale_max)
    write_raw(writer, d.size_scale_min)
    write_raw(writer, d.size_scale_max)
    write_raw(writer, d.selection_group)
    write_raw(writer, d.probability)
    write_raw(writer, d.description_index)


def default_description_record() -> DescriptionRecord:
    return DescriptionRecord(
        name=WireString(decoded="", raw_bytes=b"", encoding="utf8", framing=None, valid=True, changed=True),
        component_type=make_raw_u8(0),
        flags=make_raw_bitset(0, 2),
        legacy_transform=default_legacy_transform(),
        lod=make_raw_u8(1),  # parser default per effdir.md ParseDescRecOptions
        lod_range=make_raw_u8(6),  # parser default
        shell_count=make_raw_u16(1),
        shell_delay=make_raw_u16(16),
        emit_scale_min=make_raw_f32(1.0),
        emit_scale_max=make_raw_f32(1.0),
        size_scale_min=make_raw_f32(1.0),
        size_scale_max=make_raw_f32(1.0),
        selection_group=make_raw_u16(0),
        probability=make_raw_u16(0),
        description_index=make_raw_u32(0xFFFFFFFF),
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
