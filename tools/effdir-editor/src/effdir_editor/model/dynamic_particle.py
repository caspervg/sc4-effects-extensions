"""cSC4DynamicParticleDescription (Read 0x004B8ADA); present only for
major version 4 (effdir.md, "Dynamic particle"). The major-4 version gate
belongs in the top-level resource reader, not here.

Wire order (effdir.md, "Dynamic particle"):
    bitset<7>@+0x08, string@+0x0c, f32@+0x10, f32@+0x14,
    f32@+0x18, f32@+0x1c, f32@+0x20, f32@+0x24,
    u32@+0x28, vector<u32>@+0x2c

Member names from the dynamic-particle parser cross-reference (effdir.md,
"Major-4 dynamic-particle descriptor"): `base_name` (+0x0c), `mass`
(+0x10), `friction_min`/`friction_max` (+0x18/+0x1c), `angular_friction`
(+0x20), `model_key` (+0x28), `model_keys` vector (+0x2c). `+0x08` flags
and `+0x24` have no traced consumer, so `+0x24` is left as `value_24`
per the doc's own naming (the flags word is named `flags` since its
role as a bitset, not its bit meanings, is established).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..wire import (
    Raw,
    ReadCursor,
    WireString,
    WireVector,
    WriteCursor,
    make_raw_bitset,
    make_raw_f32,
    make_raw_u32,
    read_bitset,
    read_f32,
    read_u32,
    read_vector,
    read_wire_string,
    write_raw,
    write_vector,
    write_wire_string,
)

_U32 = 4


@dataclass
class DynamicParticleDescriptor:
    flags: Raw[int]  # bitset<7>; bit meanings not traced
    base_name: WireString
    mass: Raw[float]
    value_14: Raw[float]
    friction_min: Raw[float]
    friction_max: Raw[float]
    angular_friction: Raw[float]
    value_24: Raw[float]
    model_key: Raw[int]
    model_keys: WireVector[int]


def read_dynamic_particle(cursor: ReadCursor) -> DynamicParticleDescriptor:
    return DynamicParticleDescriptor(
        flags=read_bitset(cursor, 7),
        base_name=read_wire_string(cursor),
        mass=read_f32(cursor),
        value_14=read_f32(cursor),
        friction_min=read_f32(cursor),
        friction_max=read_f32(cursor),
        angular_friction=read_f32(cursor),
        value_24=read_f32(cursor),
        model_key=read_u32(cursor),
        model_keys=read_vector(cursor, ReadCursor.u32, element_size=_U32),
    )


def write_dynamic_particle(writer: WriteCursor, d: DynamicParticleDescriptor) -> None:
    write_raw(writer, d.flags)
    write_wire_string(writer, d.base_name)
    write_raw(writer, d.mass)
    write_raw(writer, d.value_14)
    write_raw(writer, d.friction_min)
    write_raw(writer, d.friction_max)
    write_raw(writer, d.angular_friction)
    write_raw(writer, d.value_24)
    write_raw(writer, d.model_key)
    write_vector(writer, d.model_keys, WriteCursor.u32)


def default_dynamic_particle() -> DynamicParticleDescriptor:
    """No documented constructor defaults; zero/empty for every member."""

    return DynamicParticleDescriptor(
        flags=make_raw_bitset(0, 7),
        base_name=WireString(decoded="", raw_bytes=b"", encoding="utf8", framing=None, valid=True, changed=True),
        mass=make_raw_f32(0.0),
        value_14=make_raw_f32(0.0),
        friction_min=make_raw_f32(0.0),
        friction_max=make_raw_f32(0.0),
        angular_friction=make_raw_f32(0.0),
        value_24=make_raw_f32(0.0),
        model_key=make_raw_u32(0),
        model_keys=WireVector(count=0, items=[], source_span=None),
    )
