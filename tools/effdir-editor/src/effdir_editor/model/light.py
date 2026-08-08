"""cSC4LightDescription (reader/writer pair at 0x003FC6EC).

Wire order (effdir.md, "Shake and light"):
    vector<cS3DVector3>, vector<f32>, f32

Member names from the light parser cross-reference (effdir.md, "Light
descriptor"): `color` vector (+0x00), `strength` vector (+0x0c), `length`
(+0x18).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..wire import (
    Raw,
    ReadCursor,
    Vec3,
    WireVector,
    WriteCursor,
    make_raw_f32,
    read_f32,
    read_vec3,
    read_vector,
    write_raw,
    write_vec3,
    write_vector,
)

_F32 = 4
_VEC3 = 12


@dataclass
class LightDescriptor:
    color: WireVector[Vec3]
    strength: WireVector[float]
    length: Raw[float]


def read_light(cursor: ReadCursor) -> LightDescriptor:
    return LightDescriptor(
        color=read_vector(cursor, read_vec3, element_size=_VEC3),
        strength=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        length=read_f32(cursor),
    )


def write_light(writer: WriteCursor, l: LightDescriptor) -> None:
    write_vector(writer, l.color, write_vec3)
    write_vector(writer, l.strength, WriteCursor.f32)
    write_raw(writer, l.length)


def default_light() -> LightDescriptor:
    """Constructor defaults (cSC4LightDescription::cSC4LightDescription,
    0x00760A72): color and strength vectors start empty, length defaults
    to 2.0."""

    return LightDescriptor(
        color=WireVector(count=0, items=[], source_span=None),
        strength=WireVector(count=0, items=[], source_span=None),
        length=make_raw_f32(2.0),
    )
