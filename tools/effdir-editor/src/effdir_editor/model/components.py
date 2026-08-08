"""Component records: brush, attractor, scrubber, sequence, sound, camera.

Wire order per effdir.md, "Component records", cross-checked against
Ghidra Read() decompiles for each class (see per-class notes below).
Sequence bits 0-2 and camera bits 0-3 are read via a generic operator>>
(bitset<N>) rather than a direct scalar dispatch, matching the documented
bit options, but this makes no wire-byte difference (bitsets always
occupy one u32) so those two fields keep generic `value_XX` names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..wire import (
    Raw,
    ReadCursor,
    RecordPreservation,
    Vec2,
    WireString,
    WireVector,
    WriteCursor,
    make_raw_bitset,
    make_raw_f32,
    make_raw_u16,
    make_raw_u32,
    make_raw_u8,
    read_bitset,
    read_f32,
    read_u8,
    read_u16,
    read_u32,
    read_vec2,
    read_vector,
    read_wire_string,
    write_raw,
    write_vec2,
    write_vector,
    write_wire_string,
)

_U32 = 4
_F32 = 4


# --- brush: u16 marker(Write=0), u32@0c, f32@10, f32@14, u8@18, u32@1c, ---
# --- Vec2@20, Vec2@28, f32@30 ---------------------------------------------
#
# Ghidra cSC4BrushDescription::Read (0x003e2938) confirms strength/width are
# each a single Vec2 (x=min, y=max), not a Bounds2 pair -- effdir.md's
# "-strength minimum/maximum" phrasing describes the Vec2's two components,
# not two nested Vec2s. Modeling these as Bounds2 (16 bytes) instead of Vec2
# (8 bytes) corrupted every brush read after the first.


@dataclass
class BrushDescription:
    marker: Raw[int]
    key: Raw[int]  # +0x0c, "-name" resource key
    rate: Raw[float]  # +0x10
    length: Raw[float]  # +0x14
    mode: Raw[int]  # +0x18, "-apply"
    zoom: Raw[int]  # +0x1c, "-zoom" minus one
    strength: Vec2  # +0x20, "-strength" (x=min, y=max)
    width: Vec2  # +0x28, "-width" (x=min, y=max)
    level: Raw[float]  # +0x30


def read_brush(cursor: ReadCursor) -> BrushDescription:
    return BrushDescription(
        marker=read_u16(cursor),
        key=read_u32(cursor),
        rate=read_f32(cursor),
        length=read_f32(cursor),
        mode=read_u8(cursor),
        zoom=read_u32(cursor),
        strength=read_vec2(cursor),
        width=read_vec2(cursor),
        level=read_f32(cursor),
    )


def write_brush(writer: WriteCursor, b: BrushDescription) -> None:
    write_raw(writer, b.marker)
    write_raw(writer, b.key)
    write_raw(writer, b.rate)
    write_raw(writer, b.length)
    write_raw(writer, b.mode)
    write_raw(writer, b.zoom)
    write_vec2(writer, b.strength)
    write_vec2(writer, b.width)
    write_raw(writer, b.level)


def default_brush() -> BrushDescription:
    return BrushDescription(
        marker=make_raw_u16(0),
        key=make_raw_u32(0),
        rate=make_raw_f32(0.0),
        length=make_raw_f32(0.0),
        mode=make_raw_u8(0),
        zoom=make_raw_u32(0),
        strength=Vec2(0.0, 0.0),
        width=Vec2(0.0, 0.0),
        level=make_raw_f32(0.0),
    )


# --- attractor: u16 marker(Write=0), string@0c, u8 selector ---------------
#
# effdir.md documents selector as "u32@+0x10", but empirically (real
# vanilla attractors: "waterhose_repulser" selector=1, "sim_plop_jump"
# selector=0) it is a single byte -- a u32 read consumes 3 bytes of the
# next record's marker/length, corrupting every subsequent attractor.


@dataclass
class AttractorDescription:
    marker: Raw[int]
    name: WireString  # +0x0c, "-name"/"-group" string
    selector: Raw[int]  # u8; "-group" sets 1


def read_attractor(cursor: ReadCursor) -> AttractorDescription:
    return AttractorDescription(marker=read_u16(cursor), name=read_wire_string(cursor), selector=read_u8(cursor))


def write_attractor(writer: WriteCursor, a: AttractorDescription) -> None:
    write_raw(writer, a.marker)
    write_wire_string(writer, a.name)
    write_raw(writer, a.selector)


def default_attractor() -> AttractorDescription:
    return AttractorDescription(
        marker=make_raw_u16(0),
        name=WireString(decoded="", raw_bytes=b"", encoding="utf8", framing=None, valid=True, changed=True),
        selector=make_raw_u8(0),
    )


# --- scrubber: u16 marker(Write=1), then the field list below -------------
#
# Ghidra cSC4ScrubberDescription::Read (0x003e1ae2) shows the WIRE order
# diverges from ascending object offset: message_1/message_2/shape/
# shape_value_3c/shape_bounds/shape_value_48/pause_duration are read BEFORE
# conditional_28/value_2c, which come last, both gated on marker != 0 (not
# just conditional_28 -- effdir-editor-spec.md's typed schema draft is wrong
# to mark only one of the pair optional). +0xc is read via a generic
# operator>> (a bitset<7>, matching the documented scrubber bit options),
# not a plain u32.


@dataclass
class ScrubberDescription:
    marker: Raw[int]
    flags: Raw[int]  # +0xc, bitset<7>: noNetworks/noFlora/dezone/single/pauseSim/pauseSimHidden/pauseClock
    value_10: Raw[int]
    value_14: Raw[int]  # "-demolish"
    action: Raw[int]  # +0x18, demolition action/effect packed value
    min_size: Raw[float]  # +0x1c, "-minDemolishSize"
    max_size: Raw[float]  # +0x20, "-maxDemolishSize"
    value_24: Raw[int]  # "-toxic"
    message_1: Raw[int]  # +0x30
    message_2: Raw[int]  # +0x34
    shape: Raw[int]  # +0x38, "-blob"/"-rect" selector
    shape_value_3c: Raw[float]
    shape_bounds: Vec2  # +0x40
    shape_value_48: Raw[float]
    pause_duration: Raw[float]  # +0x4c
    conditional_28: Optional[Raw[int]]  # read only if marker != 0, at the END of the record
    value_2c: Optional[Raw[int]]  # also gated on marker != 0
    preservation: RecordPreservation = field(default_factory=RecordPreservation)


def read_scrubber(cursor: ReadCursor) -> ScrubberDescription:
    marker = read_u16(cursor)
    flags = read_bitset(cursor, 7)
    value_10 = read_u32(cursor)
    value_14 = read_u32(cursor)
    action = read_u32(cursor)
    min_size = read_f32(cursor)
    max_size = read_f32(cursor)
    value_24 = read_u32(cursor)
    message_1 = read_u32(cursor)
    message_2 = read_u32(cursor)
    shape = read_u32(cursor)
    shape_value_3c = read_f32(cursor)
    shape_bounds = read_vec2(cursor)
    shape_value_48 = read_f32(cursor)
    pause_duration = read_f32(cursor)
    has_conditional = marker.value != 0
    conditional_28 = read_u32(cursor) if has_conditional else None
    value_2c = read_u32(cursor) if has_conditional else None
    return ScrubberDescription(
        marker=marker,
        flags=flags,
        value_10=value_10,
        value_14=value_14,
        action=action,
        min_size=min_size,
        max_size=max_size,
        value_24=value_24,
        message_1=message_1,
        message_2=message_2,
        shape=shape,
        shape_value_3c=shape_value_3c,
        shape_bounds=shape_bounds,
        shape_value_48=shape_value_48,
        pause_duration=pause_duration,
        conditional_28=conditional_28,
        value_2c=value_2c,
    )


def write_scrubber(writer: WriteCursor, s: ScrubberDescription) -> None:
    write_raw(writer, s.marker)
    write_raw(writer, s.flags)
    write_raw(writer, s.value_10)
    write_raw(writer, s.value_14)
    write_raw(writer, s.action)
    write_raw(writer, s.min_size)
    write_raw(writer, s.max_size)
    write_raw(writer, s.value_24)
    write_raw(writer, s.message_1)
    write_raw(writer, s.message_2)
    write_raw(writer, s.shape)
    write_raw(writer, s.shape_value_3c)
    write_vec2(writer, s.shape_bounds)
    write_raw(writer, s.shape_value_48)
    write_raw(writer, s.pause_duration)
    # Mirror read_scrubber's marker condition so read/write always agree,
    # including after an edit to marker (see class docstring note).
    if s.marker.value != 0:
        write_raw(writer, s.conditional_28 if s.conditional_28 is not None else make_raw_u32(0))
        write_raw(writer, s.value_2c if s.value_2c is not None else make_raw_u32(0))


def default_scrubber() -> ScrubberDescription:
    return ScrubberDescription(
        marker=make_raw_u16(1),
        flags=make_raw_bitset(0, 7),
        value_10=make_raw_u32(0),
        value_14=make_raw_u32(0),
        action=make_raw_u32(0),
        min_size=make_raw_f32(0.0),
        max_size=make_raw_f32(0.0),
        value_24=make_raw_u32(0),
        message_1=make_raw_u32(0),
        message_2=make_raw_u32(0),
        shape=make_raw_u32(0),
        shape_value_3c=make_raw_f32(0.0),
        shape_bounds=Vec2(0.0, 0.0),
        shape_value_48=make_raw_f32(0.0),
        pause_duration=make_raw_f32(0.0),
        conditional_28=make_raw_u32(0),
        value_2c=make_raw_u32(0),
    )


# --- sequence: u16 marker(Write=1), vector<SequenceItem>@0c, u32@18 -------


@dataclass(frozen=True)
class SequenceItem:
    timing: Vec2  # wait/play timing values
    effect_name: WireString  # play effect name


def read_sequence_item(cursor: ReadCursor) -> SequenceItem:
    return SequenceItem(timing=read_vec2(cursor), effect_name=read_wire_string(cursor))


def write_sequence_item(writer: WriteCursor, item: SequenceItem) -> None:
    write_vec2(writer, item.timing)
    write_wire_string(writer, item.effect_name)


@dataclass
class SequenceDescription:
    marker: Raw[int]
    items: WireVector[SequenceItem]
    value_18: Raw[int]  # likely carries loop/noOverlap/hardStart bits; unconfirmed
    preservation: RecordPreservation = field(default_factory=RecordPreservation)


def read_sequence(cursor: ReadCursor) -> SequenceDescription:
    return SequenceDescription(
        marker=read_u16(cursor),
        items=read_vector(cursor, read_sequence_item),
        value_18=read_u32(cursor),
    )


def write_sequence(writer: WriteCursor, s: SequenceDescription) -> None:
    write_raw(writer, s.marker)
    write_vector(writer, s.items, write_sequence_item)
    write_raw(writer, s.value_18)


def default_sequence() -> SequenceDescription:
    return SequenceDescription(
        marker=make_raw_u16(1),
        items=WireVector(count=0, items=[], source_span=None),
        value_18=make_raw_u32(0),
    )


# --- sound: u16 marker(Write=0), u32@0c, u32@10, f32@14, f32@18 -----------


@dataclass
class SoundDescription:
    marker: Raw[int]
    value_0c: Raw[int]
    resource_key: Raw[int]  # +0x10, "-name"
    location_update_rate: Raw[float]  # +0x14, inverse "-locationUpdateRate"
    length: Raw[float]  # +0x18


def read_sound(cursor: ReadCursor) -> SoundDescription:
    return SoundDescription(
        marker=read_u16(cursor),
        value_0c=read_u32(cursor),
        resource_key=read_u32(cursor),
        location_update_rate=read_f32(cursor),
        length=read_f32(cursor),
    )


def write_sound(writer: WriteCursor, s: SoundDescription) -> None:
    write_raw(writer, s.marker)
    write_raw(writer, s.value_0c)
    write_raw(writer, s.resource_key)
    write_raw(writer, s.location_update_rate)
    write_raw(writer, s.length)


def default_sound() -> SoundDescription:
    return SoundDescription(
        marker=make_raw_u16(0),
        value_0c=make_raw_u32(0),
        resource_key=make_raw_u32(0),
        location_update_rate=make_raw_f32(0.0),
        length=make_raw_f32(0.0),
    )


# --- camera: u16 marker(Write=0), u32@0c, u8@10, u8@11, f32@14 ------------


@dataclass
class CameraDescription:
    marker: Raw[int]
    value_0c: Raw[int]
    value_10: Raw[int]  # zoom-minus-one or rotation value (union-like)
    value_11: Raw[int]
    attach_radius: Raw[float]  # +0x14


def read_camera(cursor: ReadCursor) -> CameraDescription:
    return CameraDescription(
        marker=read_u16(cursor),
        value_0c=read_u32(cursor),
        value_10=read_u8(cursor),
        value_11=read_u8(cursor),
        attach_radius=read_f32(cursor),
    )


def write_camera(writer: WriteCursor, c: CameraDescription) -> None:
    write_raw(writer, c.marker)
    write_raw(writer, c.value_0c)
    write_raw(writer, c.value_10)
    write_raw(writer, c.value_11)
    write_raw(writer, c.attach_radius)


def default_camera() -> CameraDescription:
    return CameraDescription(
        marker=make_raw_u16(0),
        value_0c=make_raw_u32(0),
        value_10=make_raw_u8(0),
        value_11=make_raw_u8(0),
        attach_radius=make_raw_f32(0.0),
    )


# --- collection: six vectors in fixed order -------------------------------


@dataclass
class ComponentCollections:
    brushes: WireVector[BrushDescription]
    attractors: WireVector[AttractorDescription]
    scrubbers: WireVector[ScrubberDescription]
    sequences: WireVector[SequenceDescription]
    sounds: WireVector[SoundDescription]
    cameras: WireVector[CameraDescription]


def read_component_collections(cursor: ReadCursor) -> ComponentCollections:
    return ComponentCollections(
        brushes=read_vector(cursor, read_brush),
        attractors=read_vector(cursor, read_attractor),
        scrubbers=read_vector(cursor, read_scrubber),
        sequences=read_vector(cursor, read_sequence),
        sounds=read_vector(cursor, read_sound),
        cameras=read_vector(cursor, read_camera),
    )


def write_component_collections(writer: WriteCursor, c: ComponentCollections) -> None:
    write_vector(writer, c.brushes, write_brush)
    write_vector(writer, c.attractors, write_attractor)
    write_vector(writer, c.scrubbers, write_scrubber)
    write_vector(writer, c.sequences, write_sequence)
    write_vector(writer, c.sounds, write_sound)
    write_vector(writer, c.cameras, write_camera)


def default_component_collections() -> ComponentCollections:
    return ComponentCollections(
        brushes=WireVector(count=0, items=[], source_span=None),
        attractors=WireVector(count=0, items=[], source_span=None),
        scrubbers=WireVector(count=0, items=[], source_span=None),
        sequences=WireVector(count=0, items=[], source_span=None),
        sounds=WireVector(count=0, items=[], source_span=None),
        cameras=WireVector(count=0, items=[], source_span=None),
    )
