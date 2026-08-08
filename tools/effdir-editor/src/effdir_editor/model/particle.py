"""cSC4ParticlesDescription (`operator>>` at 0x003F61AA, particle descriptor).

Field order and offsets are transcribed verbatim from effdir.md's wire dump
for the particle descriptor. Names come from effdir.md's parser
cross-reference table where a command handler is traced to a member;
everything else keeps a `value_<offset>` placeholder name rather than a
guessed one, per the "field names are intentionally mixed" policy in
effdir-editor-spec.md.

Two members are documented shared storage, each written by more than one
source spelling (effdir-editor-spec.md, "Command-oriented interpretation"
examples table):

- `+0x150` (`collision_effect_or_death`): `effect` and `death` options of
  `cParticleCollisionCommand`.
- `+0x1d4` (`model_speed_static`): the bullet list in effdir.md notes that
  `modelSpeed`/`modelSpeedStatic` "use the same model-speed storage", but
  the wire dump shows two adjacent floats (+0x1d0, +0x1d4) and the typed
  schema in effdir-editor-spec.md names both. Both are kept as distinct
  wire members; the shared-storage note is preserved here as a caveat, not
  collapsed into one field.

The three leading bitsets are the "leading bitset" / "second bitset" /
"third bitset" referenced throughout effdir.md's parser cross-reference;
they are kept as opaque `Raw<bitset<N>>` values here. Individual bit
meanings belong to the command-binding catalog (`bindings/catalog.py`),
not to this wire-accurate model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..wire import (
    Raw,
    ReadCursor,
    RecordPreservation,
    Vec2,
    Vec3,
    Bounds3,
    WireString,
    WireVector,
    WriteCursor,
    make_raw_bitset,
    make_raw_f32,
    make_raw_u8,
    make_raw_u16,
    make_raw_u32,
    read_bitset,
    read_bounds3,
    read_f32,
    read_u8,
    read_u16,
    read_u32,
    read_vec2,
    read_vec3,
    read_vector,
    read_wire_string,
    write_bounds3,
    write_raw,
    write_vec2,
    write_vec3,
    write_vector,
    write_wire_string,
)
from .common import (
    TimedEffect,
    TractorPoint,
    Wiggle,
    read_timed_effect,
    read_tractor_point,
    read_wiggle,
    write_timed_effect,
    write_tractor_point,
    write_wiggle,
)

_VEC2 = 8
_VEC3 = 12
_BOUNDS3 = 24
_WIGGLE = 28
_TRACTOR_POINT = 32
_U32 = 4
_F32 = 4


@dataclass
class ParticleDescriptor:
    flags_0: Raw[int]  # bitset<32>, "leading bitset" in effdir.md
    flags_1: Raw[int]  # bitset<8>, "second bitset"
    flags_2: Raw[int]  # bitset<11>, "third bitset"
    life: Vec2  # +0x00c/+0x010, cParticleLifeCommand life min/max
    value_014: Raw[float]
    value_018: Raw[int]
    preroll: Raw[float]  # +0x01c, cParticleLifeCommand
    value_020: Vec2
    value_028: Vec2
    value_030: Bounds3
    value_048: Vec2
    source_bounds: Bounds3  # +0x050, cParticleSourceCommand emission region
    size_vary: Raw[float]  # +0x068, cParticleSizeCommand
    aspect_vary: Raw[float]  # +0x06c, cParticleAspectCommand
    rotate_vary: Raw[float]  # +0x070, cParticleRotateCommand
    rotate_offset: Raw[float]  # +0x074, cParticleRotateCommand
    alpha_vary: Raw[float]  # +0x078, cParticleAlphaCommand
    color_vary: Vec3  # +0x07c, cParticleColorCommand vary vector
    emit_curve: WireVector[float]  # +0x088, emit/maintain/inject shared storage
    color_curve: WireVector[Vec3]  # +0x094, cParticleColorCommand
    alpha_curve: WireVector[float]  # +0x0a0, cParticleAlphaCommand
    size_curve: WireVector[float]  # +0x0ac, size-over-time
    aspect_curve: WireVector[float]  # +0x0b8, aspect-over-time
    rotate_curve: WireVector[float]  # +0x0c4, rotate-over-time
    resource_key: Raw[int]  # +0x0d0, texture/model shared resource key
    draw_mode: Raw[int]  # +0x0d4, model draw option (parser writes 3)
    alignment_mode: Raw[int]  # +0x0d5, cParticleAlignmentCommand
    value_0d8: Raw[float]
    value_0dc: Raw[float]
    force: Vec3  # +0x0e0, cParticleForceCommand accumulated gravity/wind
    global_wind: Raw[float]  # +0x0ec
    bomb: Raw[float]  # +0x0f0
    bomb_direction: Vec3  # +0x0f4
    drag: Raw[float]  # +0x100
    screw: Raw[float]  # +0x104
    wiggles: WireVector[Wiggle]  # +0x108, cParticleWarpCommand
    uv_scale: Raw[float]  # +0x114
    uv_range: Vec2  # +0x118
    alpha_warp_direction: Vec3  # +0x120
    alpha_warp_curve: WireVector[float]  # +0x12c
    bounce: Raw[float]  # +0x138, cParticleCollisionCommand (default 0.3)
    terrain_repel: Vec2  # +0x13c/+0x140, cParticleTerrainRepelCommand
    scout: Raw[float]  # +0x144
    vertical: Raw[float]  # +0x148
    kill_height: Raw[float]  # +0x14c
    collision_effect_or_death: Raw[float]  # +0x150, shared: effect / death
    death_by_water: Raw[float]  # +0x154
    height_range: Vec2  # +0x158, source belowHeight/aboveHeight/heightRange
    terrain_name: WireString  # +0x160
    value_164: Raw[int]
    value_166: Raw[int]
    value_168: Raw[float]
    random_walk_delay: Vec2  # +0x16c/+0x170
    random_walk_strength: Vec2  # +0x174/+0x178
    random_walk_turn: Vec2  # +0x17c/+0x180
    prefer_direction: Vec3  # +0x184, random-walk preferDir
    alignment_damp: Raw[float]  # +0x190
    bank_range: Vec2  # +0x194/+0x198, alignment bank/windBank
    attractor_curve: WireVector[float]  # +0x19c
    attractor_strength: Raw[float]  # +0x1a8
    value_1ac: Raw[int]
    tractor_points: WireVector[TractorPoint]  # +0x1b0
    tractor_reset_speed: Raw[float]  # +0x1bc
    timed_effects: WireVector[TimedEffect]  # +0x1c4
    model_speed: Raw[float]  # +0x1d0
    model_speed_static: Raw[float]  # +0x1d4, see module docstring caveat
    model_keys: WireVector[int]  # +0x1d8
    explosion: Raw[float]  # +0x1e4
    explosion_front_secondary: Raw[float]  # +0x1e8
    explosion_curve: WireVector[float]  # +0x1ec
    explosion_front: Raw[float]  # +0x1f8
    preservation: RecordPreservation = field(default_factory=RecordPreservation)


def read_particle(cursor: ReadCursor) -> ParticleDescriptor:
    return ParticleDescriptor(
        flags_0=read_bitset(cursor, 32),
        flags_1=read_bitset(cursor, 8),
        flags_2=read_bitset(cursor, 11),
        life=read_vec2(cursor),
        value_014=read_f32(cursor),
        value_018=read_u32(cursor),
        preroll=read_f32(cursor),
        value_020=read_vec2(cursor),
        value_028=read_vec2(cursor),
        value_030=read_bounds3(cursor),
        value_048=read_vec2(cursor),
        source_bounds=read_bounds3(cursor),
        size_vary=read_f32(cursor),
        aspect_vary=read_f32(cursor),
        rotate_vary=read_f32(cursor),
        rotate_offset=read_f32(cursor),
        alpha_vary=read_f32(cursor),
        color_vary=read_vec3(cursor),
        emit_curve=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        color_curve=read_vector(cursor, read_vec3, element_size=_VEC3),
        alpha_curve=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        size_curve=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        aspect_curve=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        rotate_curve=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        resource_key=read_u32(cursor),
        draw_mode=read_u8(cursor),
        alignment_mode=read_u8(cursor),
        value_0d8=read_f32(cursor),
        value_0dc=read_f32(cursor),
        force=read_vec3(cursor),
        global_wind=read_f32(cursor),
        bomb=read_f32(cursor),
        bomb_direction=read_vec3(cursor),
        drag=read_f32(cursor),
        screw=read_f32(cursor),
        wiggles=read_vector(cursor, read_wiggle, element_size=_WIGGLE),
        uv_scale=read_f32(cursor),
        uv_range=read_vec2(cursor),
        alpha_warp_direction=read_vec3(cursor),
        alpha_warp_curve=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        bounce=read_f32(cursor),
        terrain_repel=read_vec2(cursor),
        scout=read_f32(cursor),
        vertical=read_f32(cursor),
        kill_height=read_f32(cursor),
        collision_effect_or_death=read_f32(cursor),
        death_by_water=read_f32(cursor),
        height_range=read_vec2(cursor),
        terrain_name=read_wire_string(cursor),
        value_164=read_u16(cursor),
        value_166=read_u16(cursor),
        value_168=read_f32(cursor),
        random_walk_delay=read_vec2(cursor),
        random_walk_strength=read_vec2(cursor),
        random_walk_turn=read_vec2(cursor),
        prefer_direction=read_vec3(cursor),
        alignment_damp=read_f32(cursor),
        bank_range=read_vec2(cursor),
        attractor_curve=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        attractor_strength=read_f32(cursor),
        value_1ac=read_u32(cursor),
        tractor_points=read_vector(cursor, read_tractor_point, element_size=_TRACTOR_POINT),
        tractor_reset_speed=read_f32(cursor),
        timed_effects=read_vector(cursor, read_timed_effect),
        model_speed=read_f32(cursor),
        model_speed_static=read_f32(cursor),
        model_keys=read_vector(cursor, ReadCursor.u32, element_size=_U32),
        explosion=read_f32(cursor),
        explosion_front_secondary=read_f32(cursor),
        explosion_curve=read_vector(cursor, ReadCursor.f32, element_size=_F32),
        explosion_front=read_f32(cursor),
    )


def write_particle(writer: WriteCursor, p: ParticleDescriptor) -> None:
    write_raw(writer, p.flags_0)
    write_raw(writer, p.flags_1)
    write_raw(writer, p.flags_2)
    write_vec2(writer, p.life)
    write_raw(writer, p.value_014)
    write_raw(writer, p.value_018)
    write_raw(writer, p.preroll)
    write_vec2(writer, p.value_020)
    write_vec2(writer, p.value_028)
    write_bounds3(writer, p.value_030)
    write_vec2(writer, p.value_048)
    write_bounds3(writer, p.source_bounds)
    write_raw(writer, p.size_vary)
    write_raw(writer, p.aspect_vary)
    write_raw(writer, p.rotate_vary)
    write_raw(writer, p.rotate_offset)
    write_raw(writer, p.alpha_vary)
    write_vec3(writer, p.color_vary)
    write_vector(writer, p.emit_curve, WriteCursor.f32)
    write_vector(writer, p.color_curve, write_vec3)
    write_vector(writer, p.alpha_curve, WriteCursor.f32)
    write_vector(writer, p.size_curve, WriteCursor.f32)
    write_vector(writer, p.aspect_curve, WriteCursor.f32)
    write_vector(writer, p.rotate_curve, WriteCursor.f32)
    write_raw(writer, p.resource_key)
    write_raw(writer, p.draw_mode)
    write_raw(writer, p.alignment_mode)
    write_raw(writer, p.value_0d8)
    write_raw(writer, p.value_0dc)
    write_vec3(writer, p.force)
    write_raw(writer, p.global_wind)
    write_raw(writer, p.bomb)
    write_vec3(writer, p.bomb_direction)
    write_raw(writer, p.drag)
    write_raw(writer, p.screw)
    write_vector(writer, p.wiggles, write_wiggle)
    write_raw(writer, p.uv_scale)
    write_vec2(writer, p.uv_range)
    write_vec3(writer, p.alpha_warp_direction)
    write_vector(writer, p.alpha_warp_curve, WriteCursor.f32)
    write_raw(writer, p.bounce)
    write_vec2(writer, p.terrain_repel)
    write_raw(writer, p.scout)
    write_raw(writer, p.vertical)
    write_raw(writer, p.kill_height)
    write_raw(writer, p.collision_effect_or_death)
    write_raw(writer, p.death_by_water)
    write_vec2(writer, p.height_range)
    write_wire_string(writer, p.terrain_name)
    write_raw(writer, p.value_164)
    write_raw(writer, p.value_166)
    write_raw(writer, p.value_168)
    write_vec2(writer, p.random_walk_delay)
    write_vec2(writer, p.random_walk_strength)
    write_vec2(writer, p.random_walk_turn)
    write_vec3(writer, p.prefer_direction)
    write_raw(writer, p.alignment_damp)
    write_vec2(writer, p.bank_range)
    write_vector(writer, p.attractor_curve, WriteCursor.f32)
    write_raw(writer, p.attractor_strength)
    write_raw(writer, p.value_1ac)
    write_vector(writer, p.tractor_points, write_tractor_point)
    write_raw(writer, p.tractor_reset_speed)
    write_vector(writer, p.timed_effects, write_timed_effect)
    write_raw(writer, p.model_speed)
    write_raw(writer, p.model_speed_static)
    write_vector(writer, p.model_keys, WriteCursor.u32)
    write_raw(writer, p.explosion)
    write_raw(writer, p.explosion_front_secondary)
    write_vector(writer, p.explosion_curve, WriteCursor.f32)
    write_raw(writer, p.explosion_front)


def default_particle() -> ParticleDescriptor:
    """Constructor-equivalent defaults for a newly added particle.

    Only the two defaults effdir.md documents from the executable
    constructor are applied (emit curve `[25]`, color curve `[white]`);
    everything else is zeroed. These are convenience values, not semantic
    claims (effdir-editor-spec.md, "Add a particle or other descriptor").
    """

    zero_f32 = lambda: make_raw_f32(0.0)
    zero_u32 = lambda: make_raw_u32(0)
    zero_u16 = lambda: make_raw_u16(0)
    zero_u8 = lambda: make_raw_u8(0)
    zero_vec2 = lambda: Vec2(0.0, 0.0)
    zero_vec3 = lambda: Vec3(0.0, 0.0, 0.0)
    zero_bounds3 = lambda: Bounds3(zero_vec3(), zero_vec3())

    return ParticleDescriptor(
        flags_0=make_raw_bitset(0, 32),
        flags_1=make_raw_bitset(0, 8),
        flags_2=make_raw_bitset(0, 11),
        life=zero_vec2(),
        value_014=zero_f32(),
        value_018=zero_u32(),
        preroll=zero_f32(),
        value_020=zero_vec2(),
        value_028=zero_vec2(),
        value_030=zero_bounds3(),
        value_048=zero_vec2(),
        source_bounds=zero_bounds3(),
        size_vary=zero_f32(),
        aspect_vary=zero_f32(),
        rotate_vary=zero_f32(),
        rotate_offset=zero_f32(),
        alpha_vary=zero_f32(),
        color_vary=zero_vec3(),
        emit_curve=WireVector(count=1, items=[25.0], source_span=None),
        color_curve=WireVector(count=1, items=[Vec3(1.0, 1.0, 1.0)], source_span=None),
        alpha_curve=WireVector(count=0, items=[], source_span=None),
        size_curve=WireVector(count=0, items=[], source_span=None),
        aspect_curve=WireVector(count=0, items=[], source_span=None),
        rotate_curve=WireVector(count=0, items=[], source_span=None),
        resource_key=zero_u32(),
        draw_mode=zero_u8(),
        alignment_mode=zero_u8(),
        value_0d8=zero_f32(),
        value_0dc=zero_f32(),
        force=zero_vec3(),
        global_wind=zero_f32(),
        bomb=zero_f32(),
        bomb_direction=zero_vec3(),
        drag=zero_f32(),
        screw=zero_f32(),
        wiggles=WireVector(count=0, items=[], source_span=None),
        uv_scale=zero_f32(),
        uv_range=zero_vec2(),
        alpha_warp_direction=zero_vec3(),
        alpha_warp_curve=WireVector(count=0, items=[], source_span=None),
        bounce=make_raw_f32(0.3),
        terrain_repel=zero_vec2(),
        scout=zero_f32(),
        vertical=zero_f32(),
        kill_height=zero_f32(),
        collision_effect_or_death=zero_f32(),
        death_by_water=zero_f32(),
        height_range=zero_vec2(),
        terrain_name=WireString(decoded="", raw_bytes=b"", encoding="utf8", framing=None, valid=True, changed=True),
        value_164=zero_u16(),
        value_166=zero_u16(),
        value_168=zero_f32(),
        random_walk_delay=zero_vec2(),
        random_walk_strength=zero_vec2(),
        random_walk_turn=zero_vec2(),
        prefer_direction=zero_vec3(),
        alignment_damp=zero_f32(),
        bank_range=zero_vec2(),
        attractor_curve=WireVector(count=0, items=[], source_span=None),
        attractor_strength=zero_f32(),
        value_1ac=zero_u32(),
        tractor_points=WireVector(count=0, items=[], source_span=None),
        tractor_reset_speed=zero_f32(),
        timed_effects=WireVector(count=0, items=[], source_span=None),
        model_speed=zero_f32(),
        model_speed_static=zero_f32(),
        model_keys=WireVector(count=0, items=[], source_span=None),
        explosion=zero_f32(),
        explosion_front_secondary=zero_f32(),
        explosion_curve=WireVector(count=0, items=[], source_span=None),
        explosion_front=zero_f32(),
    )
