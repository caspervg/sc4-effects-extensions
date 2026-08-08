"""cSC4EffectsResource::Read (0x003DDA9C) / ::Write (0x003DE3DA).

Top-level wire spine, effdir.md "Verified top-level wire spine" table:

 1  u16 major, u16 minor
 2  vector<ParticleDescriptor>
 3  u16 marker = 1               (marker_particles_decals)
 4  vector<DecalDescriptor>
 5  u16 marker = 0               (marker_decals_shakes)
 6  vector<ShakeDescriptor>
 7  u16 marker = 0               (marker_shakes_lights)
 8  vector<LightDescriptor>
 9  six vector<T> counts+records (brush, attractor, scrubber, sequence, sound, camera)
10  u16 marker = 1               (marker_components_dynamic)
11  vector<DynamicParticleDescriptor>, major 4 only
12  u16 marker = 2               (marker_dynamic_effects)
13  vector<EffectDescription>
14  repeated (string, u32) pairs (effect_name_map, no count prefix)
15  string "end", u32 0xFFFFFFFF (effect_name_map terminator)
16  u8 hasTrailingFloats; if nonzero: u16 marker, u32 unknown (NOT a
    count), then a FIXED 9 x f32 (TrailingFloatMetadata) -- effdir.md
    describes step 16 as "optional vector<f32>" with a runtime count, but
    no u8/u16/u32 count-width or byte-offset near the flag reproduces a
    valid count against real vanilla data. The SC4Devotion wiki's EFFDIR
    page has an unlabeled "13.5 area" (BYTE, DWORD, then nine bare FLOAT
    lines -- no "(number of reps)" annotation, unlike every counted
    section on that page) which is this same region; treating the count
    as fixed-9 and the DWORD as an uninterpreted scalar reproduces the
    real file's bytes exactly (verified against SimCity_1.dat's vanilla
    EFFDIR, including the u16 marker the wiki's list omits).
17  vector<StringU32U32Record>   (effect_key_map, normal count prefix)
18  u16 0                        (message_triggers' own group marker, same
                                  pattern as marker_particles_decals etc.;
                                  effdir.md documents this step as
                                  "u32 0 -- reserved", but Ghidra
                                  (cSC4EffectsResource::Read, tail) shows a
                                  u16 read immediately before the u32
                                  message-trigger count -- there is no
                                  separate 4-byte "reserved" scalar)
19  vector<MessageTrigger>

read_profile is selected from the minor version word (effdir.md,
"Version-1 reader paths": effect-description reader dispatches to
version-1 "when the second version word is 1"). Major must be 3 or 4;
major 3 skips step 11 entirely (effdir-editor-spec.md, "Parsing contract").

Unsupported major version or any other wire error falls back to a
raw-preserved resource (preservation.original_payload set, all fields
defaulted): the editor can still inspect it but write_resource returns
the original bytes verbatim rather than guess a layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from ..wire import (
    CursorError,
    Diagnostic,
    PreservationData,
    Raw,
    ReadCursor,
    WireVector,
    WriteCursor,
    empty_vector,
    make_raw_u16,
    make_raw_u32,
    make_raw_u8,
    read_u8,
    read_u16,
    read_u32,
    read_vector,
    write_raw,
    write_vector,
)
from .common import (
    MessageTrigger,
    ReadProfile,
    StringU32Pair,
    StringU32U32Record,
    Version,
    make_version,
    read_message_trigger,
    read_string_u32_pair,
    read_string_u32_u32_record,
    read_version,
    write_message_trigger,
    write_string_u32_pair,
    write_string_u32_u32_record,
    write_version,
)
from .components import (
    ComponentCollections,
    default_component_collections,
    read_component_collections,
    write_component_collections,
)
from .decal import DecalDescriptor, default_decal, read_decal, write_decal
from .dynamic_particle import (
    DynamicParticleDescriptor,
    read_dynamic_particle,
    write_dynamic_particle,
)
from .effect import (
    EffectDescription,
    read_effect_description,
    write_effect_description,
)
from .light import LightDescriptor, read_light, write_light
from .particle import ParticleDescriptor, read_particle, write_particle
from .shake import ShakeDescriptor, read_shake, write_shake

_EFFECT_NAME_MAP_TERMINATOR = b"end"
_EFFECT_NAME_MAP_TERMINATOR_TARGET = 0xFFFFFFFF
_TRAILING_FLOAT_COUNT = 9  # fixed; see module docstring, step 16


class UnsupportedVersionError(ValueError):
    pass


@dataclass(frozen=True)
class TrailingFloatMetadata:
    """Step 16 of the top-level spine. See module docstring: this is not
    a runtime vector<f32> despite effdir.md's description -- `marker` and
    `unknown` are only present when `present.value != 0`, and `values` is
    always exactly 9 floats when present, never a stored count."""

    present: Raw[int]  # u8
    marker: Optional[Raw[int]]  # u16
    unknown: Optional[Raw[int]]  # u32; not a count
    values: Optional[Tuple[float, ...]]  # exactly _TRAILING_FLOAT_COUNT f32


def read_trailing_float_metadata(cursor: ReadCursor) -> TrailingFloatMetadata:
    present = read_u8(cursor)
    if present.value == 0:
        return TrailingFloatMetadata(present=present, marker=None, unknown=None, values=None)
    marker = read_u16(cursor)
    unknown = read_u32(cursor)
    values = tuple(cursor.f32() for _ in range(_TRAILING_FLOAT_COUNT))
    return TrailingFloatMetadata(present=present, marker=marker, unknown=unknown, values=values)


def write_trailing_float_metadata(writer: WriteCursor, t: TrailingFloatMetadata) -> None:
    write_raw(writer, t.present)
    if t.present.value != 0:
        write_raw(writer, t.marker)
        write_raw(writer, t.unknown)
        for v in t.values:
            writer.f32(v)


@dataclass
class EffDirResource:
    version: Version
    read_profile: ReadProfile
    particles: WireVector[ParticleDescriptor]
    marker_particles_decals: Raw[int]
    decals: WireVector[DecalDescriptor]
    marker_decals_shakes: Raw[int]
    shakes: WireVector[ShakeDescriptor]
    marker_shakes_lights: Raw[int]
    lights: WireVector[LightDescriptor]
    components: ComponentCollections
    marker_components_dynamic: Raw[int]
    dynamic_particles: WireVector[DynamicParticleDescriptor]
    marker_dynamic_effects: Raw[int]
    effect_descriptions: WireVector[EffectDescription]
    effect_name_map: WireVector[StringU32Pair]
    trailing_float_metadata: TrailingFloatMetadata
    effect_key_map: WireVector[StringU32U32Record]
    marker_key_map_triggers: Raw[int]  # message_triggers' own group marker
    message_triggers: WireVector[MessageTrigger]
    preservation: PreservationData = field(default_factory=PreservationData)


def _read_effect_name_map(cursor: ReadCursor, *, hard_limit: int) -> WireVector[StringU32Pair]:
    start = cursor.pos
    items = []
    while True:
        entry = read_string_u32_pair(cursor)
        if entry.name.raw_bytes == _EFFECT_NAME_MAP_TERMINATOR and entry.target.value == _EFFECT_NAME_MAP_TERMINATOR_TARGET:
            break
        items.append(entry)
        if len(items) > hard_limit:
            raise CursorError(f"effect name map exceeded hard limit {hard_limit} without a terminator")
    return WireVector(count=len(items), items=items, source_span=cursor.span_since(start))


def _write_effect_name_map(writer: WriteCursor, vec: WireVector[StringU32Pair]) -> None:
    from ..wire import WireString

    for item in vec.items:
        write_string_u32_pair(writer, item)
    write_string_u32_pair(
        writer,
        StringU32Pair(name=WireString.from_text("end"), target=make_raw_u32(_EFFECT_NAME_MAP_TERMINATOR_TARGET)),
    )


def _raw_fallback(data: bytes, error: Exception) -> EffDirResource:
    return EffDirResource(
        version=make_version(0, 0),
        read_profile=ReadProfile.CURRENT,
        particles=empty_vector(),
        marker_particles_decals=make_raw_u16(0),
        decals=empty_vector(),
        marker_decals_shakes=make_raw_u16(0),
        shakes=empty_vector(),
        marker_shakes_lights=make_raw_u16(0),
        lights=empty_vector(),
        components=default_component_collections(),
        marker_components_dynamic=make_raw_u16(0),
        dynamic_particles=empty_vector(),
        marker_dynamic_effects=make_raw_u16(0),
        effect_descriptions=empty_vector(),
        effect_name_map=empty_vector(),
        trailing_float_metadata=TrailingFloatMetadata(present=make_raw_u8(0), marker=None, unknown=None, values=None),
        effect_key_map=empty_vector(),
        marker_key_map_triggers=make_raw_u16(0),
        message_triggers=empty_vector(),
        preservation=PreservationData(
            original_payload=data,
            diagnostics=[Diagnostic(severity="error", code="unparsed_resource", message=str(error))],
        ),
    )


def read_resource(data: bytes, *, hard_limit: int = 1 << 24) -> EffDirResource:
    cursor = ReadCursor(data)
    try:
        version = read_version(cursor)
        if version.major.value not in (3, 4):
            raise UnsupportedVersionError(f"unsupported major version {version.major.value}")
        profile = ReadProfile.VERSION1 if version.minor.value == 1 else ReadProfile.CURRENT

        particles = read_vector(cursor, read_particle)
        marker_particles_decals = read_u16(cursor)
        decals = read_vector(cursor, read_decal)
        marker_decals_shakes = read_u16(cursor)
        shakes = read_vector(cursor, read_shake)
        marker_shakes_lights = read_u16(cursor)
        lights = read_vector(cursor, read_light)
        components = read_component_collections(cursor)
        marker_components_dynamic = read_u16(cursor)
        if version.major.value == 4:
            dynamic_particles = read_vector(cursor, read_dynamic_particle)
        else:
            dynamic_particles = empty_vector()
        marker_dynamic_effects = read_u16(cursor)
        effect_descriptions = read_vector(cursor, lambda c: read_effect_description(c, profile))
        effect_name_map = _read_effect_name_map(cursor, hard_limit=hard_limit)
        trailing_float_metadata = read_trailing_float_metadata(cursor)
        effect_key_map = read_vector(cursor, read_string_u32_u32_record)
        marker_key_map_triggers = read_u16(cursor)
        message_triggers = read_vector(cursor, read_message_trigger)

        trailing_bytes = cursor.data[cursor.pos :]
        diagnostics: list[Diagnostic] = []
        if trailing_bytes:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="trailing_bytes",
                    message=f"{len(trailing_bytes)} bytes after the documented resource end",
                )
            )

        return EffDirResource(
            version=version,
            read_profile=profile,
            particles=particles,
            marker_particles_decals=marker_particles_decals,
            decals=decals,
            marker_decals_shakes=marker_decals_shakes,
            shakes=shakes,
            marker_shakes_lights=marker_shakes_lights,
            lights=lights,
            components=components,
            marker_components_dynamic=marker_components_dynamic,
            dynamic_particles=dynamic_particles,
            marker_dynamic_effects=marker_dynamic_effects,
            effect_descriptions=effect_descriptions,
            effect_name_map=effect_name_map,
            trailing_float_metadata=trailing_float_metadata,
            effect_key_map=effect_key_map,
            marker_key_map_triggers=marker_key_map_triggers,
            message_triggers=message_triggers,
            preservation=PreservationData(trailing_bytes=trailing_bytes, diagnostics=diagnostics),
        )
    except (CursorError, UnsupportedVersionError) as e:
        return _raw_fallback(data, e)


def write_resource(resource: EffDirResource) -> bytes:
    if resource.preservation.original_payload is not None:
        return resource.preservation.original_payload

    writer = WriteCursor()
    write_version(writer, resource.version)
    write_vector(writer, resource.particles, write_particle)
    write_raw(writer, resource.marker_particles_decals)
    write_vector(writer, resource.decals, write_decal)
    write_raw(writer, resource.marker_decals_shakes)
    write_vector(writer, resource.shakes, write_shake)
    write_raw(writer, resource.marker_shakes_lights)
    write_vector(writer, resource.lights, write_light)
    write_component_collections(writer, resource.components)
    write_raw(writer, resource.marker_components_dynamic)
    if resource.version.major.value == 4:
        write_vector(writer, resource.dynamic_particles, write_dynamic_particle)
    write_raw(writer, resource.marker_dynamic_effects)
    write_vector(
        writer,
        resource.effect_descriptions,
        lambda w, e: write_effect_description(w, e, resource.read_profile),
    )
    _write_effect_name_map(writer, resource.effect_name_map)
    write_trailing_float_metadata(writer, resource.trailing_float_metadata)
    write_vector(writer, resource.effect_key_map, write_string_u32_u32_record)
    write_raw(writer, resource.marker_key_map_triggers)
    write_vector(writer, resource.message_triggers, write_message_trigger)
    writer.raw(resource.preservation.trailing_bytes)
    return writer.getvalue()


def default_resource() -> EffDirResource:
    """A fresh major-4 resource matching the game writer's version stamp
    (effdir.md: "the game's writer emits 4, 2")."""

    return EffDirResource(
        version=make_version(4, 2),
        read_profile=ReadProfile.CURRENT,
        particles=empty_vector(),
        marker_particles_decals=make_raw_u16(1),
        decals=empty_vector(),
        marker_decals_shakes=make_raw_u16(0),
        shakes=empty_vector(),
        marker_shakes_lights=make_raw_u16(0),
        lights=empty_vector(),
        components=default_component_collections(),
        marker_components_dynamic=make_raw_u16(1),
        dynamic_particles=empty_vector(),
        marker_dynamic_effects=make_raw_u16(2),
        effect_descriptions=empty_vector(),
        effect_name_map=empty_vector(),
        trailing_float_metadata=TrailingFloatMetadata(present=make_raw_u8(0), marker=None, unknown=None, values=None),
        effect_key_map=empty_vector(),
        marker_key_map_triggers=make_raw_u16(0),
        message_triggers=empty_vector(),
    )
