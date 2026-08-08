"""cSC4DecalDescription (Read 0x0076270E, Write 0x0076289E).

Wire order (effdir.md, "Decal"):
    bitset<7>, u32, u8, u8, f32,
    vector<f32>, vector<f32>, vector<f32>, vector<cS3DVector3>, vector<f32>,
    f32, f32, f32, f32, cS3DVector2

The four trailing floats before the final Vec2 are `alpha_vary` (+0x4c),
`size_vary` (+0x50), `rotate_vary` (+0x54), and `texture_repeat` (+0x58)
per the decal child parser cross-reference; the typed schema draft in
effdir-editor-spec.md only names three of the four, so `texture_repeat` is
named here from the parser table instead of left as `value_XX`.

Reader normalization quirk: the reader normalizes the second byte to 2 and
sets flag bit 6 when that byte is zero (`cSC4DecalDescription::Read`,
0x0076270E). The normalization is intentionally not replicated in the stored
wire values: `repeat_mode` and `flags` retain the exact bytes read from the
file (so an unchanged round trip never rewrites a 0 to a 2 or synthesizes bit
6), while `effective_repeat_mode()` below exposes the normalized mode for the
semantic/display layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..wire import (
    Raw,
    ReadCursor,
    RecordPreservation,
    Vec2,
    Vec3,
    WireVector,
    WriteCursor,
    make_raw_bitset,
    make_raw_f32,
    make_raw_u8,
    make_raw_u32,
    read_bitset,
    read_f32,
    read_u8,
    read_u32,
    read_vec2,
    read_vec3,
    read_vector,
    write_raw,
    write_vec2,
    write_vec3,
    write_vector,
)

_F32 = 4
_VEC3 = 12


@dataclass
class DecalDescriptor:
    flags: Raw[int]  # bitset<7>: bits 1/2/3/4/5/6 = light/water/repeat/cityScale/ring/static
    texture_key: Raw[int]
    draw_mode: Raw[int]
    repeat_mode: Raw[int]  # exact file byte; see module docstring
    life: Raw[float]
    rotation: WireVector[float]
    size: WireVector[float]
    alpha: WireVector[float]
    color: WireVector[Vec3]
    aspect: WireVector[float]
    alpha_vary: Raw[float]
    size_vary: Raw[float]
    rotate_vary: Raw[float]
    texture_repeat: Raw[float]
    texture_offset: Vec2
    preservation: RecordPreservation = field(default_factory=RecordPreservation)


def effective_repeat_mode(d: DecalDescriptor) -> int:
    """The runtime-normalized value of `repeat_mode` (0x0076270E): a
    stored 0 reads back as 2. This is a display/semantic helper only; the
    wire model keeps the original byte so writes stay lossless."""

    return 2 if d.repeat_mode.value == 0 else d.repeat_mode.value


def effective_flags(d: DecalDescriptor) -> int:
    """Runtime-normalized decal flags without modifying stored wire data.

    The reader sets the static bit (bit 6) when the stored mode byte is zero.
    Exposing that derived value separately lets the editor explain what the
    game consumes while preserving an unchanged file byte-for-byte.
    """

    return d.flags.value | (1 << 6) if d.repeat_mode.value == 0 else d.flags.value


def read_decal(cursor: ReadCursor) -> DecalDescriptor:
    return DecalDescriptor(
        flags=read_bitset(cursor, 7),
        texture_key=read_u32(cursor),
        draw_mode=read_u8(cursor),
        repeat_mode=read_u8(cursor),
        life=read_f32(cursor),
        rotation=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        size=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        alpha=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        color=read_vector(cursor, read_vec3, element_size=_VEC3),
        aspect=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        alpha_vary=read_f32(cursor),
        size_vary=read_f32(cursor),
        rotate_vary=read_f32(cursor),
        texture_repeat=read_f32(cursor),
        texture_offset=read_vec2(cursor),
    )


def write_decal(writer: WriteCursor, d: DecalDescriptor) -> None:
    write_raw(writer, d.flags)
    write_raw(writer, d.texture_key)
    write_raw(writer, d.draw_mode)
    write_raw(writer, d.repeat_mode)
    write_raw(writer, d.life)
    write_vector(writer, d.rotation, WriteCursor.f32)
    write_vector(writer, d.size, WriteCursor.f32)
    write_vector(writer, d.alpha, WriteCursor.f32)
    write_vector(writer, d.color, write_vec3)
    write_vector(writer, d.aspect, WriteCursor.f32)
    write_raw(writer, d.alpha_vary)
    write_raw(writer, d.size_vary)
    write_raw(writer, d.rotate_vary)
    write_raw(writer, d.texture_repeat)
    write_vec2(writer, d.texture_offset)


def default_decal() -> DecalDescriptor:
    """Constructor defaults (cSC4DecalDescription::cSC4DecalDescription,
    0x007600D2): life 5.0, rotate/size/alpha/aspect curves seeded with one
    value each, color curve seeded white, zero variation, texture_repeat
    1.0, zero offset."""

    return DecalDescriptor(
        flags=make_raw_bitset(0, 7),
        texture_key=make_raw_u32(0),
        draw_mode=make_raw_u8(0),
        repeat_mode=make_raw_u8(0),
        life=make_raw_f32(5.0),
        rotation=WireVector(count=1, items=[0.0], source_span=None),
        size=WireVector(count=1, items=[1.0], source_span=None),
        alpha=WireVector(count=1, items=[1.0], source_span=None),
        color=WireVector(count=1, items=[Vec3(1.0, 1.0, 1.0)], source_span=None),
        aspect=WireVector(count=1, items=[1.0], source_span=None),
        alpha_vary=make_raw_f32(0.0),
        size_vary=make_raw_f32(0.0),
        rotate_vary=make_raw_f32(0.0),
        texture_repeat=make_raw_f32(1.0),
        texture_offset=Vec2(0.0, 0.0),
    )
