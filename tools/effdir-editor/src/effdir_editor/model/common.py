"""Small structs and top-level lookup records shared across descriptors.

Wire order for each type is given inline; see
docs/reference/binary/effdir.md and effdir-editor-spec.md for the
evidence trail. Nested record shapes (Wiggle, TractorPoint, TimedEffect)
are given in effdir-editor-spec.md's "Normative wire primitives" and
"Particle schema" sections.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..wire import (
    Raw,
    ReadCursor,
    Vec3,
    WireString,
    WriteCursor,
    make_raw_u16,
    read_u16,
    read_u32,
    read_vec3,
    read_wire_string,
    write_raw,
    write_vec3,
    write_wire_string,
)
from ..wire.types import make_raw_f32, read_f32


class ReadProfile(str, Enum):
    """Which reader/writer contract a resource (or a version-gated record
    inside it) was decoded with. See effdir.md, "Version-1 reader paths"."""

    CURRENT = "current"
    VERSION1 = "version1"


@dataclass(frozen=True)
class Version:
    major: Raw[int]
    minor: Raw[int]


def read_version(cursor: ReadCursor) -> Version:
    return Version(major=read_u16(cursor), minor=read_u16(cursor))


def write_version(writer: WriteCursor, v: Version) -> None:
    write_raw(writer, v.major)
    write_raw(writer, v.minor)


def make_version(major: int, minor: int) -> Version:
    return Version(major=make_raw_u16(major), minor=make_raw_u16(minor))


# --- nested records used inside particle vectors --------------------------


@dataclass(frozen=True)
class Wiggle:
    """f32, Vec3, Vec3 (28 bytes of fixed scalar payload)."""

    amount: Raw[float]
    direction: Vec3
    uv: Vec3


def read_wiggle(cursor: ReadCursor) -> Wiggle:
    return Wiggle(amount=read_f32(cursor), direction=read_vec3(cursor), uv=read_vec3(cursor))


def write_wiggle(writer: WriteCursor, w: Wiggle) -> None:
    write_raw(writer, w.amount)
    write_vec3(writer, w.direction)
    write_vec3(writer, w.uv)


@dataclass(frozen=True)
class TractorPoint:
    """Vec3, Vec3, f32 start-time, f32 end-time (32 bytes).

    The historical member names ``time`` and ``amount`` are retained for
    wire/API compatibility. The parser stores its current chain time in
    ``time`` and the segment end time in ``amount``.
    """

    position: Vec3
    direction: Vec3
    time: Raw[float]
    amount: Raw[float]


def read_tractor_point(cursor: ReadCursor) -> TractorPoint:
    return TractorPoint(
        position=read_vec3(cursor),
        direction=read_vec3(cursor),
        time=read_f32(cursor),
        amount=read_f32(cursor),
    )


def write_tractor_point(writer: WriteCursor, t: TractorPoint) -> None:
    write_vec3(writer, t.position)
    write_vec3(writer, t.direction)
    write_raw(writer, t.time)
    write_raw(writer, t.amount)


@dataclass(frozen=True)
class TimedEffect:
    """string, f32."""

    effect_name: WireString
    time: Raw[float]


def read_timed_effect(cursor: ReadCursor) -> TimedEffect:
    return TimedEffect(effect_name=read_wire_string(cursor), time=read_f32(cursor))


def write_timed_effect(writer: WriteCursor, t: TimedEffect) -> None:
    write_wire_string(writer, t.effect_name)
    write_raw(writer, t.time)


# --- top-level lookup/key maps and message triggers ------------------------


@dataclass(frozen=True)
class StringU32Pair:
    """Effect-name lookup map entry: string, u32 target."""

    name: WireString
    target: Raw[int]


def read_string_u32_pair(cursor: ReadCursor) -> StringU32Pair:
    return StringU32Pair(name=read_wire_string(cursor), target=read_u32(cursor))


def write_string_u32_pair(writer: WriteCursor, e: StringU32Pair) -> None:
    write_wire_string(writer, e.name)
    write_raw(writer, e.target)


@dataclass(frozen=True)
class StringU32U32Record:
    """Effect-key map entry: string, u32 group, u32 instance. Real vanilla
    data shows entries sharing one group_id across sequential instance_id
    values for related effects (e.g. demolish_building_small/medium/large
    all share a group_id with instance_id 1/2/3) -- this is how the binary
    format expresses the effect "families" the text format names."""

    name: WireString
    group_id: Raw[int]
    instance_id: Raw[int]


def read_string_u32_u32_record(cursor: ReadCursor) -> StringU32U32Record:
    return StringU32U32Record(name=read_wire_string(cursor), group_id=read_u32(cursor), instance_id=read_u32(cursor))


def write_string_u32_u32_record(writer: WriteCursor, e: StringU32U32Record) -> None:
    write_wire_string(writer, e.name)
    write_raw(writer, e.group_id)
    write_raw(writer, e.instance_id)


@dataclass(frozen=True)
class MessageTrigger:
    """cSC4MessageTriggerDescription: u32, string."""

    message_id: Raw[int]
    effect_name: WireString


def read_message_trigger(cursor: ReadCursor) -> MessageTrigger:
    return MessageTrigger(message_id=read_u32(cursor), effect_name=read_wire_string(cursor))


def write_message_trigger(writer: WriteCursor, m: MessageTrigger) -> None:
    write_raw(writer, m.message_id)
    write_wire_string(writer, m.effect_name)
