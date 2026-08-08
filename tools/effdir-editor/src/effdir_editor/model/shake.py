"""cSC4ShakeDescription.

Wire order (effdir.md, "Shake and light"):
    f32, f32, vector<f32>, vector<f32>, f32, u8

Member names from the shake parser cross-reference (effdir.md, "Shake
descriptor"): `length` (+0x00), `fade` (+0x04), `amplitude` vector (+0x08),
`frequency` vector (+0x14), `aspect` (+0x20), `base_table` (+0x24).

Runtime confirmation: SetShakeOffsets (Mac 0x00507A20, Windows 0x007C86D0)
samples amplitude/frequency at elapsed/length, uses frequency to advance a
64-entry random or sineY table, and scales the axes by 1/aspect and aspect.
`fade` controls the early-stop tail rather than acting as a separate curve.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..wire import (
    Raw,
    ReadCursor,
    WireVector,
    WriteCursor,
    make_raw_f32,
    make_raw_u8,
    read_f32,
    read_u8,
    read_vector,
    write_raw,
    write_vector,
)

_F32 = 4


@dataclass
class ShakeDescriptor:
    length: Raw[float]
    fade: Raw[float]
    amplitude: WireVector[float]
    frequency: WireVector[float]
    aspect: Raw[float]
    base_table: Raw[int]


def read_shake(cursor: ReadCursor) -> ShakeDescriptor:
    return ShakeDescriptor(
        length=read_f32(cursor),
        fade=read_f32(cursor),
        amplitude=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        frequency=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        aspect=read_f32(cursor),
        base_table=read_u8(cursor),
    )


def write_shake(writer: WriteCursor, s: ShakeDescriptor) -> None:
    write_raw(writer, s.length)
    write_raw(writer, s.fade)
    write_vector(writer, s.amplitude, WriteCursor.f32)
    write_vector(writer, s.frequency, WriteCursor.f32)
    write_raw(writer, s.aspect)
    write_raw(writer, s.base_table)


def default_shake() -> ShakeDescriptor:
    """Constructor defaults (cSC4ShakeDescription::cSC4ShakeDescription,
    0x0075E1F0): amplitude and frequency vectors start empty. No other
    defaults are documented; length/fade/aspect/base_table are zeroed."""

    return ShakeDescriptor(
        length=make_raw_f32(0.0),
        fade=make_raw_f32(0.0),
        amplitude=WireVector(count=0, items=[], source_span=None),
        frequency=WireVector(count=0, items=[], source_span=None),
        aspect=make_raw_f32(0.0),
        base_table=make_raw_u8(0),
    )
