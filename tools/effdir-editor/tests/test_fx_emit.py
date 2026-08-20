import dataclasses

import pytest

from effdir_editor.fx import Coverage, emit_effect_closure, emit_resource
from effdir_editor.fx.bits import bit
from effdir_editor.fx.names import resolve_names
from effdir_editor.fx.writer import FxWriter, fmt_hex, fmt_num, fmt_vec3_sample, is_emittable_float, quote_name
from effdir_editor.model.common import ReadProfile, StringU32Pair, StringU32U32Record, MessageTrigger
from effdir_editor.model.components import default_attractor, default_brush, default_camera, default_scrubber, default_sequence, default_sound
from effdir_editor.model.decal import default_decal
from effdir_editor.model.dynamic_particle import default_dynamic_particle
from effdir_editor.model.effect import LegacyTransform, Matrix3, default_description_record, default_effect_description, default_event_record
from effdir_editor.model.light import default_light
from effdir_editor.model.particle import default_particle
from effdir_editor.model.resource import TrailingFloatMetadata, default_resource, read_resource, write_resource
from effdir_editor.model.shake import default_shake
from effdir_editor.wire import Vec2, Vec3, WireString, WireVector, make_raw_bitset, make_raw_f32, make_raw_u8, make_raw_u32, make_raw_u16


# --- writer -----------------------------------------------------------------


def test_fmt_num_strips_float32_noise_and_trailing_zeros():
    assert fmt_num(0.30000001192092896) == "0.3"
    assert fmt_num(2.0) == "2"
    assert fmt_num(-0.0) == "0"
    assert fmt_num(1.5) == "1.5"


def test_fmt_vec3_sample_and_hex():
    # A vector is always one quoted argument -- ParseVector3 reads all three
    # components out of a single argument string.
    assert fmt_vec3_sample(Vec3(1.0, 2.0, 3.0)) == '"1 2 3"'
    assert fmt_hex(0x1A) == "0x0000001a"


def test_quote_name_only_quotes_when_needed():
    assert quote_name("plain_name") == "plain_name"
    assert quote_name("has space") == '"has space"'
    assert quote_name("") == '""'


def test_writer_blocks_are_closed_but_commands_stay_on_one_line():
    # Only the top-level definitions and effect children are `end`-closed
    # blocks (docs/syntax/blocks-and-scopes.md); a command with switches is
    # one line, so it can never close its enclosing block by accident.
    w = FxWriter()
    w.begin("particles foo")
    w.line("life 1 2")
    w.begin_command("collision")
    w.line("-bounce 0.5")
    w.line("-sticky")
    w.end_command()
    w.end()
    w.command(["brushEffect -name x", "-rate 1"])
    assert w.text().splitlines() == [
        "particles foo",
        "    life 1 2",
        "    collision -bounce 0.5 -sticky",
        "end",
        "brushEffect -name x -rate 1",
    ]


def test_bit_helper():
    assert bit(0b1010, 1) is True
    assert bit(0b1010, 0) is False


# --- coverage -----------------------------------------------------------------


def test_coverage_ratio_and_summary():
    c = Coverage()
    c.emitted()
    c.emitted()
    c.skipped("path.a", "no spelling")
    assert c.fields_considered == 3
    assert c.fields_emitted == 2
    assert c.ratio == 2 / 3
    assert any("unsupported" in line for line in c.summary_lines())


def test_coverage_empty_is_full_ratio():
    assert Coverage().ratio == 1.0


# --- names --------------------------------------------------------------------


def test_resolve_names_synthesizes_orphan_names_without_coverage_noise():
    r = default_resource()
    r.particles.items.append(default_particle())
    coverage = Coverage()
    names = resolve_names(r, coverage)
    assert names.by_collection[("particles", 0)] == "particle_0"
    assert not coverage.notes


def test_resolve_names_uses_description_record_name():
    r = default_resource()
    r.particles.items.append(default_particle())
    eff = default_effect_description()
    child = dataclasses.replace(
        default_description_record(),
        name=WireString.from_text("my_particle"),
        component_type=make_raw_u8(0),
        description_index=make_raw_u32(0),
    )
    eff = dataclasses.replace(eff, descriptions=WireVector(count=1, items=[child], source_span=None))
    r.effect_descriptions.items.append(eff)

    coverage = Coverage()
    names = resolve_names(r, coverage)
    assert names.by_collection[("particles", 0)] == "my_particle"


def test_resolve_names_uses_one_alias_for_each_brush_resource_key():
    r = default_resource()
    r.components.brushes.items.extend(
        [
            dataclasses.replace(default_brush(), key=make_raw_u32(0x1234)),
            dataclasses.replace(default_brush(), key=make_raw_u32(0x1234)),
        ]
    )

    coverage = Coverage()
    names = resolve_names(r, coverage)
    assert names.by_collection[("components.brushes", 0)] == "brush_0"
    assert names.by_collection[("components.brushes", 1)] == "brush_0"


# --- particles ------------------------------------------------------------------


def _resource_with_one_particle(particle):
    r = default_resource()
    r.particles.items.append(particle)
    eff = default_effect_description()
    child = dataclasses.replace(
        default_description_record(),
        name=WireString.from_text("p"),
        component_type=make_raw_u8(0),
        description_index=make_raw_u32(0),
    )
    eff = dataclasses.replace(eff, descriptions=WireVector(count=1, items=[child], source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("Owner"), target=make_raw_u32(0)))
    return r


def test_particle_size_curve_inverts_the_parser_x50_transform():
    p = dataclasses.replace(default_particle(), size_curve=WireVector(count=2, items=[50.0, 100.0], source_span=None))
    result = emit_resource(_resource_with_one_particle(p))
    assert "size 1 2" in result.text


def test_particle_inject_bit_emits_confirmed_inject_mode():
    p = dataclasses.replace(
        default_particle(),
        flags_0=make_raw_bitset(1 << 1, 32),
        emit_curve=WireVector(count=1, items=[10.0], source_span=None),
    )
    result = emit_resource(_resource_with_one_particle(p))
    assert "emit -inject 10" in result.text
    assert "emit -rate" not in result.text


def test_particle_maintain_bit_takes_priority_over_emit_bit():
    p = dataclasses.replace(
        default_particle(),
        flags_0=make_raw_bitset((1 << 1) | (1 << 2), 32),
        emit_curve=WireVector(count=1, items=[7.5], source_span=None),
    )
    result = emit_resource(_resource_with_one_particle(p))
    assert "maintain 7.5" in result.text
    assert "emit -rate" not in result.text


def test_particle_collision_effect_death_uses_exact_canonical_spelling_without_noise():
    p = dataclasses.replace(
        default_particle(),
        flags_0=make_raw_bitset(1 << 8, 32),
        collision_effect_or_death=make_raw_f32(0.7),
    )
    result = emit_resource(_resource_with_one_particle(p))
    assert "-effect 0.7" in result.text
    assert not [n for n in result.coverage.notes if "collision_effect_or_death" in n.path]


def test_particle_texture_vs_model_dispatch():
    textured = dataclasses.replace(default_particle(), resource_key=make_raw_u32(0xAA))
    result = emit_resource(_resource_with_one_particle(textured))
    assert "textureID tex_000000aa 0x000000aa" in result.text
    assert "texture tex_000000aa" in result.text

    modeled = dataclasses.replace(default_particle(), flags_2=make_raw_bitset(1, 11), resource_key=make_raw_u32(0xBB))
    result2 = emit_resource(_resource_with_one_particle(modeled))
    assert "modelID mdl_000000bb 0x000000bb" in result2.text
    assert "model mdl_000000bb" in result2.text
    assert "texture mdl_000000bb" not in result2.text
    assert not [n for n in result.coverage.notes if "original textureID" in n.message]
    assert not [n for n in result2.coverage.notes if "original modelID" in n.message]


def test_particle_source_bounds_use_lossless_canonical_box_without_noise():
    p = dataclasses.replace(default_particle(), source_bounds=dataclasses.replace(default_particle().source_bounds, minimum=Vec3(-2, -2, -2), maximum=Vec3(2, 2, 2)))
    result = emit_resource(_resource_with_one_particle(p))
    assert "-point" not in result.text
    assert 'source -box "2 2 2"' in result.text
    assert not [n for n in result.coverage.notes if "source_bounds" in n.path]


def test_particle_random_walk_and_terrain_repel():
    p = dataclasses.replace(
        default_particle(),
        flags_0=make_raw_bitset((1 << 23) | (1 << 24) | (1 << 10), 32),
        random_walk_delay=Vec2(0.1, 0.2),
        terrain_repel=Vec2(1.0, 2.0),
    )
    result = emit_resource(_resource_with_one_particle(p))
    assert "randomWalk" in result.text
    assert "-delay 0.1 0.2" in result.text
    assert "-wait" in result.text
    assert "terrainRepel 1 2" in result.text


# --- decal/shake/light/dynamicParticle/sequence smoke tests --------------------


def test_decal_omits_default_appearance_curves_but_emits_changed_life():
    r = default_resource()
    r.decals.items.append(dataclasses.replace(default_decal(), life=make_raw_f32(4.0)))
    result = emit_resource(r)
    assert "decal decal_0" in result.text
    assert "life 4" in result.text
    assert "color " not in result.text


@pytest.mark.parametrize(
    ("mode", "static", "expected"),
    [
        (1, False, "life 5 -loop"),
        (1, True, "life 5 -static"),
        (2, False, "life 5 -single"),
        (3, True, "life 5 -static -sustain"),
    ],
)
def test_decal_life_playback_mode_is_reconstructed(mode, static, expected):
    r = default_resource()
    flags = (1 << 6) if static else 0
    r.decals.items.append(
        dataclasses.replace(default_decal(), repeat_mode=make_raw_u8(mode), flags=make_raw_bitset(flags, 7))
    )

    result = emit_resource(r)

    assert expected in result.text
    assert not [n for n in result.coverage.notes if "repeat_mode" in n.path]


def test_scrubber_action_and_map_shape_are_reconstructed():
    r = default_resource()
    r.components.scrubbers.items.append(
        dataclasses.replace(
            default_scrubber(),
            action=make_raw_u32(0x1302),
            map_index=make_raw_u32(3),
            map_value=make_raw_f32(5.0),
            map_half_extents=Vec2(2.0, 2.0),
            map_spread=make_raw_f32(4.0),
        )
    )
    child = dataclasses.replace(
        default_description_record(),
        name=WireString.from_text("scrub"),
        component_type=make_raw_u8(5),
        description_index=make_raw_u32(0),
    )
    eff = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[child], source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))

    result = emit_resource(r)

    assert "-blob 3 5 2 4" in result.text
    assert "-explode" in result.text
    assert not [n for n in result.coverage.notes if n.path.endswith(".action") or n.path.endswith(".map_index")]


def test_constructor_default_commands_are_omitted():
    r = default_resource()
    r.particles.items.append(default_particle())
    r.decals.items.append(default_decal())
    r.lights.items.append(default_light())
    r.dynamic_particles.items.append(default_dynamic_particle())

    text = emit_resource(r).text

    assert "emit -rate" not in text
    assert "color " not in text
    assert "alpha " not in text
    assert "size " not in text
    assert "life " not in text
    assert "length 2" not in text
    assert "mass 1" not in text
    assert "force" not in text
    assert "warp" not in text


def test_particle_color_vary_is_one_grouped_vector_argument():
    p = dataclasses.replace(default_particle(), color_vary=Vec3(0.1, 0.2, 0.3))

    result = emit_resource(_resource_with_one_particle(p))

    assert 'color "1 1 1" -vary "0.1 0.2 0.3"' in result.text
    assert not [n for n in result.coverage.notes if n.path.endswith(".color_vary")]


def test_random_walk_omits_constructor_valued_options():
    p = dataclasses.replace(default_particle(), flags_0=make_raw_bitset(1 << 23, 32))

    result = emit_resource(_resource_with_one_particle(p))
    block = result.text.split("randomWalk", 1)[1].split("end", 1)[0]

    assert "-delay" not in block
    assert "-strength" not in block
    assert "-turn" not in block


def test_shake_emits_table_only_for_non_default():
    r = default_resource()
    r.shakes.items.append(dataclasses.replace(default_shake(), base_table=make_raw_u8(1)))
    result = emit_resource(r)
    assert "table sineY" in result.text


def test_shake_table_random_default_is_not_emitted():
    r = default_resource()
    r.shakes.items.append(default_shake())
    result = emit_resource(r)
    assert "table random" not in result.text


def test_light_emits_strength_length_color():
    r = default_resource()
    r.lights.items.append(dataclasses.replace(default_light(), length=make_raw_f32(2.5)))
    result = emit_resource(r)
    assert "length 2.5" in result.text
    assert "-fade" not in result.text


def test_dynamic_particle_emits_effect_base_and_friction():
    r = default_resource()
    r.dynamic_particles.items.append(
        dataclasses.replace(default_dynamic_particle(), base_name=WireString.from_text("base_fx"), friction_min=make_raw_f32(0.1), friction_max=make_raw_f32(0.2))
    )
    result = emit_resource(r)
    assert "effectBase base_fx" in result.text
    assert "friction 0.1 0.2 -angular 0" in result.text


def test_sequence_emits_wait_and_play():
    from effdir_editor.model.components import SequenceItem

    r = default_resource()
    seq = dataclasses.replace(
        default_sequence(),
        items=WireVector(
            count=2,
            items=[SequenceItem(timing=Vec2(1.0, 0.0), effect_name=WireString.from_text("")), SequenceItem(timing=Vec2(0.0, 0.0), effect_name=WireString.from_text("boom"))],
            source_span=None,
        ),
    )
    r.components.sequences.items.append(seq)
    result = emit_resource(r)
    assert "wait 1 0" in result.text
    assert "play boom 0 0" in result.text


# --- effects --------------------------------------------------------------------


def test_effect_top_level_switches_and_priority():
    r = default_resource()
    eff = dataclasses.replace(default_effect_description(), flags=make_raw_bitset((1 << 0) | (1 << 3), 9), priority=make_raw_u32(2))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_resource(r)
    assert "effect E viewRelative rigid -priority 2" in result.text


def test_effect_version1_profile_omits_start_message():
    r = default_resource()
    r.read_profile = ReadProfile.VERSION1
    eff = dataclasses.replace(default_effect_description(), start_message_1=make_raw_u32(5))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_resource(r)
    assert "-startMessage" not in result.text


def test_effect_constructor_start_message_debug_fill_is_omitted():
    r = default_resource()
    r.effect_descriptions.items.append(default_effect_description())
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_resource(r)
    assert "-priority" not in result.text
    assert "-startMessage" not in result.text


def test_effect_start_message_trims_only_trailing_debug_fill():
    r = default_resource()
    eff = dataclasses.replace(
        default_effect_description(),
        start_message_1=make_raw_u32(7),
        start_message_2=make_raw_u32(0xCCCCCCCC),
        start_message_3=make_raw_u32(0xCCCCCCCC),
    )
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_resource(r)
    assert "-startMessage 0x00000007" in result.text
    assert "3435973836" not in result.text


def test_effect_start_message_formats_type_as_hex_and_payloads_as_decimal():
    r = default_resource()
    eff = dataclasses.replace(
        default_effect_description(),
        start_message_1=make_raw_u32(0xAC400A31),
        start_message_2=make_raw_u32(12),
        start_message_3=make_raw_u32(34),
    )
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))

    assert "-startMessage 0xac400a31 12 34" in emit_resource(r).text


def test_effect_select_group_wraps_children():
    r = default_resource()
    r.particles.items.append(default_particle())
    r.decals.items.append(default_decal())
    a = dataclasses.replace(default_description_record(), name=WireString.from_text("pa"), component_type=make_raw_u8(0), description_index=make_raw_u32(0), selection_group=make_raw_u16(1))
    b = dataclasses.replace(default_description_record(), name=WireString.from_text("db"), component_type=make_raw_u8(1), description_index=make_raw_u32(0), selection_group=make_raw_u16(1))
    eff = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=2, items=[a, b], source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_resource(r)
    lines = [ln.strip() for ln in result.text.splitlines()]
    select_idx = lines.index("select")
    assert lines[select_idx + 1] == "particleEffect pa"
    assert lines[select_idx + 2] == "decalEffect db"
    assert lines[select_idx + 3] == "end"


def test_select_probability_and_system_sequence_are_reconstructed():
    r = default_resource()
    r.particles.items.append(default_particle())
    child = dataclasses.replace(
        default_description_record(),
        name=WireString.from_text("p"),
        component_type=make_raw_u8(0),
        description_index=make_raw_u32(0),
        flags=make_raw_bitset(1 << 1, 2),
        selection_group=make_raw_u16(1),
        probability=make_raw_u16(32768),
    )
    eff = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[child], source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))

    result = emit_resource(r)

    assert "particleSequence\n        select" in result.text
    assert "particleEffect p -prob 0.500008" in result.text
    assert not [n for n in result.coverage.notes if "probability" in n.path or "systemSequence" in n.message]


def test_lod_pair_and_parser_rotation_matrix_are_inverted():
    r = default_resource()
    r.particles.items.append(default_particle())
    transform = LegacyTransform(
        matrix=Matrix3(row_0=Vec3(0, -1, 0), row_1=Vec3(1, 0, 0), row_2=Vec3(0, 0, 1)),
        translation=Vec3(0, 0, 0),
        scale=1.0,
        revision=make_raw_u32(0),
    )
    child = dataclasses.replace(
        default_description_record(),
        name=WireString.from_text("p"),
        component_type=make_raw_u8(0),
        description_index=make_raw_u32(0),
        legacy_transform=transform,
        lod=make_raw_u8(2),
        lod_range=make_raw_u8(5),
    )
    eff = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[child], source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))

    result = emit_resource(r)

    assert "-lodRange 2 4" in result.text
    assert "-rotateXYZ 0 0 90" in result.text
    assert not [n for n in result.coverage.notes if "legacy_transform.matrix" in n.path or "lod_range" in n.path]


def test_effect_events_dispatch_shake_flash_tint():
    r = default_resource()
    r.shakes.items.append(default_shake())
    r.lights.items.append(default_light())
    events = [
        dataclasses.replace(default_event_record(), flags=make_raw_bitset(1 << 0, 4), name=WireString.from_text("s"), value=make_raw_u32(0)),
        dataclasses.replace(default_event_record(), flags=make_raw_bitset((1 << 1) | (1 << 2), 4), name=WireString.from_text("f"), time=make_raw_f32(200.0), value=make_raw_u32(0)),
        dataclasses.replace(default_event_record(), flags=make_raw_bitset(1 << 3, 4), name=WireString.from_text("t"), value=make_raw_u32(0)),
    ]
    eff = dataclasses.replace(default_effect_description(), events=WireVector(count=3, items=events, source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_resource(r)
    assert "shakeEffect s -noEpicentre" in result.text
    assert "flashEffect f -epicentre 200" in result.text
    assert "tintEffect t" in result.text


def test_effect_non_identity_transform_is_not_guessed_at():
    r = default_resource()
    r.particles.items.append(default_particle())
    rotated = LegacyTransform(matrix=Matrix3(row_0=Vec3(0, 1, 0), row_1=Vec3(1, 0, 0), row_2=Vec3(0, 0, 1)), translation=Vec3(0, 0, 0), scale=1.0, revision=make_raw_u32(0))
    child = dataclasses.replace(default_description_record(), name=WireString.from_text("p"), component_type=make_raw_u8(0), description_index=make_raw_u32(0), legacy_transform=rotated)
    eff = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[child], source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_resource(r)
    assert "-rotate" not in result.text
    assert any(n.severity == "unsupported" and "legacy_transform.matrix" in n.path for n in result.coverage.notes)


def test_visual_effect_component_is_name_based_while_unknown_type_is_skipped():
    r = default_resource()
    visual = dataclasses.replace(default_description_record(), name=WireString.from_text("x"), component_type=make_raw_u8(2), description_index=make_raw_u32(0))
    unknown = dataclasses.replace(default_description_record(), name=WireString.from_text("y"), component_type=make_raw_u8(200), description_index=make_raw_u32(0))
    eff = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=2, items=[visual, unknown], source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_resource(r)
    assert "effect E" in result.text
    assert "visualEffect x" in result.text
    unsupported_paths = [n.path for n in result.coverage.notes if n.severity == "unsupported"]
    assert "effect_descriptions[0].descriptions[0]" not in unsupported_paths
    assert "effect_descriptions[0].descriptions[1]" in unsupported_paths


def test_sequence_definition_and_effect_child_use_distinct_keywords():
    r = default_resource()
    r.components.sequences.items.append(default_sequence())
    child = dataclasses.replace(
        default_description_record(),
        name=WireString.from_text("seq"),
        component_type=make_raw_u8(6),
        description_index=make_raw_u32(0),
    )
    eff = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[child], source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))

    text = emit_resource(r).text

    # Definition is `sequence`, the effect child that references it is
    # `sequenceEffect` -- they are registered in different command tables.
    assert "sequence seq" in text
    assert "sequenceEffect seq" in text


def test_camera_and_repeated_brush_inline_components_emit_full_fields():
    r = default_resource()
    r.components.brushes.items.append(dataclasses.replace(default_brush(), rate=make_raw_f32(3.0)))
    r.components.cameras.items.append(dataclasses.replace(default_camera(), attach_radius=make_raw_f32(5.0)))
    first = dataclasses.replace(default_description_record(), name=WireString.from_text("br"), component_type=make_raw_u8(3), description_index=make_raw_u32(0))
    second = dataclasses.replace(default_description_record(), name=WireString.from_text("br"), component_type=make_raw_u8(3), description_index=make_raw_u32(0))
    cam = dataclasses.replace(default_description_record(), name=WireString.from_text("c"), component_type=make_raw_u8(8), description_index=make_raw_u32(0))
    eff = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=3, items=[first, second, cam], source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_resource(r)
    assert "brushID E_brush 0x00000000" in result.text
    assert result.text.count("brushEffect -name E_brush") == 2
    assert result.text.count("-rate 3") == 2
    assert "-attachRadius 5" in result.text


def test_sound_ids_are_emitted_once_per_distinct_key():
    r = default_resource()
    r.components.sounds.items.extend(
        [
            dataclasses.replace(default_sound(), resource_key=make_raw_u32(0x12345678)),
            dataclasses.replace(default_sound(), resource_key=make_raw_u32(0x12345678)),
        ]
    )
    children = [
        dataclasses.replace(default_description_record(), component_type=make_raw_u8(7), description_index=make_raw_u32(i))
        for i in range(2)
    ]
    r.effect_descriptions.items.append(
        dataclasses.replace(default_effect_description(), descriptions=WireVector(count=2, items=children, source_span=None))
    )
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))

    text = emit_resource(r).text

    assert text.count("soundID E_sound 0x12345678") == 1
    assert text.count("-name E_sound") == 2


def test_distinct_sound_keys_in_one_effect_get_readable_unique_aliases():
    r = default_resource()
    r.components.sounds.items.extend(
        [
            dataclasses.replace(default_sound(), resource_key=make_raw_u32(1)),
            dataclasses.replace(default_sound(), resource_key=make_raw_u32(2)),
        ]
    )
    children = [
        dataclasses.replace(default_description_record(), component_type=make_raw_u8(7), description_index=make_raw_u32(i))
        for i in range(2)
    ]
    r.effect_descriptions.items.append(
        dataclasses.replace(default_effect_description(), descriptions=WireVector(count=2, items=children, source_span=None))
    )
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))

    text = emit_resource(r).text

    assert "soundID E_sound 0x00000001" in text
    assert "soundID E_sound_2 0x00000002" in text


def test_automata_effect_uses_name_stored_in_attractor_record():
    r = default_resource()
    r.components.attractors.items.append(
        dataclasses.replace(default_attractor(), name=WireString.from_text("sim_plop_jump"))
    )
    child = dataclasses.replace(
        default_description_record(),
        name=WireString.from_text(""),
        component_type=make_raw_u8(4),
        description_index=make_raw_u32(0),
    )
    r.effect_descriptions.items.append(
        dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[child], source_span=None))
    )
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))

    assert "automataEffect -name sim_plop_jump" in emit_resource(r).text


def test_camera_params_recovers_single_zoom_shorthand_and_nondefault_side_swipe():
    r = default_resource()
    r.trailing_float_metadata = TrailingFloatMetadata(
        present=make_raw_u8(1),
        marker=make_raw_u16(0),
        count=make_raw_u32(5),
        values=(5000.0, 2500.0, 1250.0, 625.0, 312.5, 100.0, 1.0, 4.0, 10.0),
    )

    text = emit_resource(r).text

    assert "camera 5000 -sideSwipe 10" in text


def test_camera_params_wire_count_is_not_assumed_to_be_five():
    r = default_resource()
    r.trailing_float_metadata = TrailingFloatMetadata(
        present=make_raw_u8(1),
        marker=make_raw_u16(0),
        count=make_raw_u32(2),
        values=(900.0, 300.0, 12.0, 2.0, 5.0, 8.0),
    )

    reread = read_resource(write_resource(r)).trailing_float_metadata

    assert reread.count.value == 2
    assert reread.values == pytest.approx((900.0, 300.0, 12.0, 2.0, 5.0, 8.0))


def test_effect_closure_emits_only_ids_needed_by_selected_effect():
    r = default_resource()
    r.components.sounds.items.extend(
        [
            dataclasses.replace(default_sound(), resource_key=make_raw_u32(1)),
            dataclasses.replace(default_sound(), resource_key=make_raw_u32(2)),
        ]
    )
    for index in range(2):
        child = dataclasses.replace(
            default_description_record(), component_type=make_raw_u8(7), description_index=make_raw_u32(index)
        )
        r.effect_descriptions.items.append(
            dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[child], source_span=None))
        )
        r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text(f"E{index}"), target=make_raw_u32(index)))

    text = emit_effect_closure(r, 1).text

    assert "soundID E1_sound 0x00000002" in text
    assert "soundID E0_sound" not in text


def test_effect_aliases_emit_visual_effect_wrapper():
    r = default_resource()
    r.effect_descriptions.items.append(default_effect_description())
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("Primary"), target=make_raw_u32(0)))
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("Alias"), target=make_raw_u32(0)))
    result = emit_resource(r)
    assert "effect Primary" in result.text
    assert "effect Alias" in result.text
    assert "visualEffect Primary" in result.text


# --- resource-level bindings and closure ---------------------------------------


def test_effect_key_map_groups_shared_group_id_as_effect_group():
    r = default_resource()
    r.effect_descriptions.items.append(default_effect_description())
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    r.effect_key_map.items.append(StringU32U32Record(name=WireString.from_text("E"), group_id=make_raw_u32(1), instance_id=make_raw_u32(1)))
    r.effect_key_map.items.append(StringU32U32Record(name=WireString.from_text("E"), group_id=make_raw_u32(1), instance_id=make_raw_u32(2)))
    result = emit_resource(r)
    assert "effectGroup" in result.text
    assert "instance 1 E" in result.text
    assert "instance 2 E" in result.text


def test_effect_key_map_singleton_uses_effect_id():
    r = default_resource()
    r.effect_descriptions.items.append(default_effect_description())
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    r.effect_key_map.items.append(StringU32U32Record(name=WireString.from_text("E"), group_id=make_raw_u32(9), instance_id=make_raw_u32(1)))
    result = emit_resource(r)
    assert "effectID 0x00000009 1 E" in result.text


def test_message_triggers_emitted():
    r = default_resource()
    r.effect_descriptions.items.append(default_effect_description())
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    r.message_triggers.items.append(MessageTrigger(message_id=make_raw_u32(0x10), effect_name=WireString.from_text("E")))
    result = emit_resource(r)
    assert "messageTrigger 0x00000010 E" in result.text


def test_emit_effect_closure_excludes_unrelated_effects_and_pools():
    r = default_resource()
    r.particles.items.append(default_particle())
    r.particles.items.append(default_particle())
    linked = dataclasses.replace(default_description_record(), name=WireString.from_text("linked"), component_type=make_raw_u8(0), description_index=make_raw_u32(0))
    unrelated = dataclasses.replace(default_description_record(), name=WireString.from_text("unrelated"), component_type=make_raw_u8(0), description_index=make_raw_u32(1))
    eff0 = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[linked], source_span=None))
    eff1 = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[unrelated], source_span=None))
    r.effect_descriptions.items.append(eff0)
    r.effect_descriptions.items.append(eff1)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("First"), target=make_raw_u32(0)))
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("Second"), target=make_raw_u32(1)))

    result = emit_effect_closure(r, 0)
    assert result is not None
    assert "particles linked" in result.text
    assert "particles unrelated" not in result.text
    assert "effect First" in result.text
    assert "effect Second" not in result.text


def test_emit_effect_closure_out_of_range_returns_none():
    r = default_resource()
    assert emit_effect_closure(r, 0) is None
    assert emit_effect_closure(r, -1) is None


# --- regression tests for defects found in review ------------------------------


def test_fmt_num_does_not_crash_on_non_finite_floats():
    # inf previously raised OverflowError from int(), aborting a whole export.
    assert fmt_num(float("inf")) == "0"
    assert fmt_num(float("-inf")) == "0"
    assert fmt_num(float("nan")) == "0"
    assert is_emittable_float(1.0) is True
    assert is_emittable_float(float("nan")) is False


def test_fmt_num_rejects_raw_wrapper_with_a_clear_error():
    with pytest.raises(TypeError, match="pass `.value`"):
        fmt_num(make_raw_f32(1.0))


def test_non_finite_floats_are_reported_not_silently_zeroed():
    p = dataclasses.replace(default_particle(), life=Vec2(float("inf"), 1.0), bounce=make_raw_f32(float("nan")))
    result = emit_resource(_resource_with_one_particle(p))
    reported = {n.path for n in result.coverage.notes if "non-finite" in n.message}
    assert "particles[0].life.x" in reported
    assert "particles[0].bounce" in reported


def test_maintain_mode_still_emits_initial_motion_options():
    # `maintain` previously returned early, dropping velocity/speed that
    # are stored in the same descriptor.
    p = dataclasses.replace(
        default_particle(),
        flags_0=make_raw_bitset(1 << 2, 32),
        emit_curve=WireVector(count=1, items=[5.0], source_span=None),
        emit_speed=Vec2(10.0, 20.0),
    )
    result = emit_resource(_resource_with_one_particle(p))
    assert "maintain 5" in result.text
    assert "-speed 10 20" in result.text


def test_unknown_particle_fields_are_reported():
    p = dataclasses.replace(
        default_particle(),
        terrain_name=WireString.from_text("some_terrain"),
        value_164=make_raw_u16(7),
        value_168=make_raw_f32(3.5),
    )
    result = emit_resource(_resource_with_one_particle(p))
    reported = {n.path for n in result.coverage.notes}
    assert "particles[0].terrain_name" not in reported
    assert "particles[0].value_164" in reported
    assert "particles[0].value_168" in reported


def test_constructor_default_unknown_fields_are_not_reported_as_noise():
    result = emit_resource(_resource_with_one_particle(default_particle()))
    reported = {n.path for n in result.coverage.notes}
    assert "particles[0].value_166" not in reported
    assert "particles[0].value_168" not in reported


def test_model_particle_does_not_flag_its_own_parser_written_draw_mode():
    p = dataclasses.replace(default_particle(), flags_2=make_raw_bitset(1, 11), resource_key=make_raw_u32(0xAB), draw_mode=make_raw_u8(3))
    result = emit_resource(_resource_with_one_particle(p))
    assert not [n for n in result.coverage.notes if "draw_mode" in n.path]


def test_non_model_draw_mode_is_still_flagged():
    p = dataclasses.replace(default_particle(), draw_mode=make_raw_u8(5))
    result = emit_resource(_resource_with_one_particle(p))
    assert [n for n in result.coverage.notes if "draw_mode" in n.path]


def test_particle_draw_and_alignment_domains_are_emitted():
    p = dataclasses.replace(
        default_particle(),
        resource_key=make_raw_u32(0xAA),
        draw_mode=make_raw_u8(5),
        alignment_mode=make_raw_u8(3),
        alignment_damp=make_raw_f32(0.25),
        bank_range=Vec2(1.0, 2.0),
        flags_2=make_raw_bitset(1 << 7, 11),
    )
    result = emit_resource(_resource_with_one_particle(p))
    assert "texture tex_000000aa -draw additive" in result.text
    assert "align dirY -damp 0.25 -windBank 1 2" in result.text


def test_force_vector_is_reproduced_as_normalized_wind():
    p = dataclasses.replace(default_particle(), force=Vec3(0.0, -9.8, 0.0))
    result = emit_resource(_resource_with_one_particle(p))
    assert '-wind "0 -1 0" 9.8' in result.text


def test_source_dice_and_model_speed_use_distinct_adjacent_fields():
    p = dataclasses.replace(
        default_particle(),
        model_speed=make_raw_f32(4.0),
        model_speed_static=make_raw_f32(2.0),
        flags_2=make_raw_bitset((1 << 0) | (1 << 6), 11),
        resource_key=make_raw_u32(0xBB),
    )
    result = emit_resource(_resource_with_one_particle(p))
    assert "source -dice 4" in result.text
    assert "-modelSpeed 2" in result.text


def test_decal_draw_domain_is_emitted():
    # The draw enum is a switch on `texture`, not a command of its own: a
    # bare `draw` line is rejected by the game with "unknown command draw".
    # kDecalDrawTypes is its own five-entry table: 2 is `modulate` here,
    # while the same value means `decalIgnoreDepth` for a particle.
    r = default_resource()
    r.decals.items.append(dataclasses.replace(default_decal(), texture_key=make_raw_u32(0xAA), draw_mode=make_raw_u8(2)))
    result = emit_resource(r)
    assert "texture tex_000000aa -draw modulate" in result.text
    assert chr(10) + "    draw " not in result.text

    # A particle-only draw value has no decal spelling and must be reported,
    # not emitted as a name the decal enum parser will reject.
    r2 = default_resource()
    r2.decals.items.append(dataclasses.replace(default_decal(), texture_key=make_raw_u32(0xAA), draw_mode=make_raw_u8(7)))
    result2 = emit_resource(r2)
    assert "-draw" not in result2.text
    assert any("draw_mode=7" in n.message for n in result2.coverage.notes)


def test_texture_and_model_keys_are_declared_before_use():
    # texture/model resolve a symbolic name through textureID/modelID; a raw
    # key makes the game reject the file with "No such texture: '0x...'".
    r = default_resource()
    r.decals.items.append(dataclasses.replace(default_decal(), texture_key=make_raw_u32(0xAA)))
    r.decals.items.append(dataclasses.replace(default_decal(), texture_key=make_raw_u32(0xAA)))
    text = emit_resource(r).text
    assert text.count("textureID tex_000000aa 0x000000aa") == 1
    assert text.index("textureID tex_000000aa") < text.index("decal ")
    assert "0x000000aa -light" not in text


def test_dynamic_particle_models_are_declared_before_use():
    from effdir_editor.model.dynamic_particle import default_dynamic_particle

    r = default_resource()
    r.dynamic_particles.items.append(
        dataclasses.replace(default_dynamic_particle(), model_key=make_raw_u32(0xCC))
    )
    text = emit_resource(r).text
    assert "modelID mdl_000000cc 0x000000cc" in text
    assert "model mdl_000000cc" in text


def test_tractor_wiggle_and_timed_effect_emit_without_crashing():
    # Each of these passed a Raw[float] wrapper straight into fmt_num.
    from effdir_editor.model.common import TimedEffect, TractorPoint, Wiggle

    p = dataclasses.replace(
        default_particle(),
        flags_0=make_raw_bitset(1 << 28, 32),
        tractor_points=WireVector(count=1, items=[TractorPoint(position=Vec3(0, 0, 0), direction=Vec3(1, 0, 0), time=make_raw_f32(0.0), amount=make_raw_f32(0.5))], source_span=None),
        wiggles=WireVector(count=1, items=[Wiggle(amount=make_raw_f32(0.4), direction=Vec3(0, 1, 0), uv=Vec3(0, 0, 0))], source_span=None),
        timed_effects=WireVector(count=1, items=[TimedEffect(effect_name=WireString.from_text("child"), time=make_raw_f32(1.5))], source_span=None),
    )
    result = emit_resource(_resource_with_one_particle(p))
    assert '-tractor "0 0 0" "1 0 0" 0.5' in result.text
    assert '-wiggleDir 0.4 "0 1 0"' in result.text
    assert "timedEffect child 1.5" in result.text


def test_closure_does_not_duplicate_a_pool_referenced_twice():
    r = default_resource()
    r.shakes.items.append(default_shake())
    events = [
        dataclasses.replace(default_event_record(), flags=make_raw_bitset(1 << 0, 4), name=WireString.from_text("quake"), value=make_raw_u32(0))
        for _ in range(2)
    ]
    eff = dataclasses.replace(default_effect_description(), events=WireVector(count=2, items=events, source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_effect_closure(r, 0)
    assert result.text.count("shake quake") == 1


def test_component_with_no_options_keeps_its_transform():
    r = default_resource()
    r.components.cameras.items.append(default_camera())  # every field zero
    transform = LegacyTransform(
        matrix=Matrix3(row_0=Vec3(1, 0, 0), row_1=Vec3(0, 1, 0), row_2=Vec3(0, 0, 1)),
        translation=Vec3(5, 6, 7),
        scale=2.0,
        revision=make_raw_u32(0),
    )
    child = dataclasses.replace(
        default_description_record(),
        name=WireString.from_text("cam"),
        component_type=make_raw_u8(8),
        description_index=make_raw_u32(0),
        legacy_transform=transform,
    )
    eff = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[child], source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_resource(r)
    assert "cameraEffect" in result.text
    assert '-offset "5 6 7"' in result.text
    assert "-scale 2" in result.text


# --- transitive closure ---------------------------------------------------------


def _chained_resource():
    """A -> particle.timedEffect -> B -> chainEffect -> C -> chainEffect -> A
    (a cycle), plus an unrelated effect D and an unrelated particle."""

    from effdir_editor.model.common import TimedEffect

    r = default_resource()
    r.particles.items.append(
        dataclasses.replace(
            default_particle(),
            timed_effects=WireVector(count=1, items=[TimedEffect(effect_name=WireString.from_text("B"), time=make_raw_f32(1.0))], source_span=None),
        )
    )
    r.particles.items.append(default_particle())  # unrelated

    child = dataclasses.replace(default_description_record(), name=WireString.from_text("sparks"), component_type=make_raw_u8(0), description_index=make_raw_u32(0))
    a = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[child], source_span=None))
    b = dataclasses.replace(default_effect_description(), chain_effect=WireString.from_text("C"))
    c = dataclasses.replace(default_effect_description(), chain_effect=WireString.from_text("A"))
    d = default_effect_description()
    for eff in (a, b, c, d):
        r.effect_descriptions.items.append(eff)
    for i, name in enumerate(["A", "B", "C", "D"]):
        r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text(name), target=make_raw_u32(i)))
    return r


def test_closure_defaults_to_single_level():
    result = emit_effect_closure(_chained_resource(), 0)
    assert "effect A" in result.text
    assert "effect B" not in result.text
    assert "effect C" not in result.text


def test_transitive_closure_follows_timed_effect_and_chain_effect():
    result = emit_effect_closure(_chained_resource(), 0, transitive=True)
    assert "effect A" in result.text
    assert "effect B" in result.text
    assert "effect C" in result.text


def test_transitive_closure_follows_visual_effect_component():
    r = default_resource()
    visual = dataclasses.replace(
        default_description_record(),
        name=WireString.from_text("B"),
        component_type=make_raw_u8(2),
        description_index=make_raw_u32(0),
    )
    a = dataclasses.replace(
        default_effect_description(),
        descriptions=WireVector(count=1, items=[visual], source_span=None),
    )
    r.effect_descriptions.items.extend([a, default_effect_description()])
    r.effect_name_map.items.extend(
        [
            StringU32Pair(name=WireString.from_text("A"), target=make_raw_u32(0)),
            StringU32Pair(name=WireString.from_text("B"), target=make_raw_u32(1)),
        ]
    )

    result = emit_effect_closure(r, 0, transitive=True)

    assert "visualEffect B" in result.text
    assert "effect A" in result.text
    assert "effect B" in result.text
    # visualEffect's target must already be defined when it is referenced
    # (docs/reference/effect-children/visual-effect.md), so B must come
    # before A even though A is the requested effect.
    assert result.text.index("effect B") < result.text.index("effect A")


def test_emit_resource_orders_visual_effect_target_before_referencing_effect():
    r = default_resource()
    visual = dataclasses.replace(
        default_description_record(),
        name=WireString.from_text("B"),
        component_type=make_raw_u8(2),
        description_index=make_raw_u32(0),
    )
    a = dataclasses.replace(
        default_effect_description(),
        descriptions=WireVector(count=1, items=[visual], source_span=None),
    )
    # A is recorded first but references B, so raw record order alone
    # would emit A before its own dependency exists.
    r.effect_descriptions.items.extend([a, default_effect_description()])
    r.effect_name_map.items.extend(
        [
            StringU32Pair(name=WireString.from_text("A"), target=make_raw_u32(0)),
            StringU32Pair(name=WireString.from_text("B"), target=make_raw_u32(1)),
        ]
    )

    text = emit_resource(r).text
    assert text.index("effect B") < text.index("effect A")


def test_transitive_closure_reports_unbreakable_cycle_as_forward_reference_note():
    result = emit_effect_closure(_chained_resource(), 0, transitive=True)
    assert any(
        "reference each other in a cycle" in n.message and n.path == "effect_descriptions[2]"
        for n in result.coverage.notes
    )


def test_transitive_closure_terminates_on_a_reference_cycle():
    # A -> B -> C -> A; each effect must appear exactly once.
    result = emit_effect_closure(_chained_resource(), 0, transitive=True)
    for name in ("A", "B", "C"):
        assert result.text.count(f"effect {name}\n") == 1


def test_transitive_closure_excludes_unreachable_effects_and_pools():
    result = emit_effect_closure(_chained_resource(), 0, transitive=True)
    assert "effect D" not in result.text
    assert result.text.count("particles ") == 1


def test_transitive_closure_reports_names_defined_in_another_resource():
    r = default_resource()
    eff = dataclasses.replace(default_effect_description(), chain_effect=WireString.from_text("lives_elsewhere"))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("X"), target=make_raw_u32(0)))
    result = emit_effect_closure(r, 0, transitive=True)
    assert any("lives_elsewhere" in n.message for n in result.coverage.notes)


def test_transitive_closure_resolves_names_case_insensitively():
    # The parser lowercases effect names before storing them.
    r = default_resource()
    a = dataclasses.replace(default_effect_description(), chain_effect=WireString.from_text("TARGET"))
    b = default_effect_description()
    r.effect_descriptions.items.append(a)
    r.effect_descriptions.items.append(b)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("start"), target=make_raw_u32(0)))
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("target"), target=make_raw_u32(1)))
    result = emit_effect_closure(r, 0, transitive=True)
    assert "effect target" in result.text


def test_emit_resource_is_syntactically_balanced():
    """A cheap sanity check that every `begin`/`multiline_command` pairs
    with a matching `end` where expected -- not a real fx parser, just a
    brace-style balance check on the two block-forming keywords the
    emitter uses (`particles`/`decal`/`shake`/`light`/`dynamicParticle`/
    `sequence`/`effect`/`select` all close with a bare `end` line)."""

    r = default_resource()
    r.particles.items.append(default_particle())
    r.decals.items.append(default_decal())
    r.shakes.items.append(default_shake())
    r.lights.items.append(default_light())
    r.dynamic_particles.items.append(default_dynamic_particle())
    r.components.sequences.items.append(default_sequence())
    r.effect_descriptions.items.append(default_effect_description())
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))

    result = emit_resource(r)
    opens = sum(1 for line in result.text.splitlines() if line.strip().split(" ")[0] in ("particles", "decal", "shake", "light", "dynamicParticle", "sequence", "effect", "select", "particleSequence"))
    closes = sum(1 for line in result.text.splitlines() if line.strip() == "end")
    assert opens == closes
    assert opens > 0


# --- highlighting vocabulary ----------------------------------------------------


def test_tokenizer_classifies_each_token_kind():
    from effdir_editor.fx import highlight

    line = 'particles spark\n    life 1 2 -preroll 0.5\n    color "1 1 1"\n    texture 0x12ab -hflip\nend'
    kinds = {(t.kind, t.text) for t in highlight.tokenize(line)}
    assert ("block", "particles") in kinds
    assert ("block", "end") in kinds
    assert ("command", "life") in kinds
    assert ("switch", "-preroll") in kinds
    assert ("number", "0.5") in kinds
    assert ("number", "0x12ab") in kinds
    assert ("string", '"1 1 1"') in kinds
    # A pool/effect name is not a keyword and must not be styled as one.
    assert not any(text == "spark" for _kind, text in kinds)


def test_tokenizer_handles_block_comments_including_multiline():
    from effdir_editor.fx import highlight

    tokens = list(highlight.tokenize("#< a\nmulti-line note #>\neffect X"))
    assert tokens[0].kind == "comment"
    assert "multi-line note" in tokens[0].text
    assert ("block", "effect") in {(t.kind, t.text) for t in tokens}


def test_tokenizer_does_not_treat_negative_numbers_as_switches():
    from effdir_editor.fx import highlight

    kinds = {(t.kind, t.text) for t in highlight.tokenize("-offset -1 2 -3")}
    assert ("switch", "-offset") in kinds
    assert ("number", "-1") in kinds
    assert ("number", "-3") in kinds


def test_tokenizer_offsets_map_back_onto_the_source_text():
    from effdir_editor.fx import highlight

    text = 'effect Boom\n    particleEffect spark -scale 2\nend'
    for token in highlight.tokenize(text):
        assert text[token.start : token.start + len(token.text)] == token.text


def test_comment_open_and_close_never_share_a_line():
    """`#<` and `#>` on one line make the game swallow the rest of the file.

    `cFileParser::DoParseFile` erases from `#<` to end of line *before*
    searching for `#>`, so a single-line comment destroys its own
    terminator and the parser stays in comment mode forever -- the file
    loads as if it were empty, with no error reported.
    """

    r = default_resource()
    r.decals.items.append(default_decal())
    text = emit_resource(r).text

    for line in text.splitlines():
        assert not ("#<" in line and "#>" in line), line
        if "#<" in line:
            assert line.strip() == "#<", line
    # And the comment still closes, so what follows is parsed.
    assert "#>" in text
    assert "decal " in _without_comments(text)


def _without_comments(text: str) -> str:
    """Drop `#<` ... `#>` blocks the way the game's line scanner does."""

    kept, in_comment = [], False
    for line in text.splitlines():
        if line.strip() == "#<":
            in_comment = True
        elif line.strip() == "#>":
            in_comment = False
        elif not in_comment:
            kept.append(line)
    return "\n".join(kept)


def test_every_block_keyword_the_emitter_produces_is_in_the_vocabulary():
    """Guards against the highlighter drifting from the emitter: any line
    that opens a block in real output must be a known block keyword."""

    from effdir_editor.fx import highlight

    r = default_resource()
    r.particles.items.append(default_particle())
    r.decals.items.append(default_decal())
    r.shakes.items.append(default_shake())
    r.lights.items.append(default_light())
    r.dynamic_particles.items.append(default_dynamic_particle())
    r.components.sequences.items.append(default_sequence())
    r.effect_descriptions.items.append(default_effect_description())
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))

    text = emit_resource(r).text
    lines = [ln.strip() for ln in _without_comments(text).splitlines() if ln.strip()]
    # Every line that is closed by a bare `end` starts with a block keyword.
    openers = {ln.split(" ")[0] for ln in lines if ln != "end" and not ln.startswith("-")}
    block_openers = {w for w in openers if w in highlight.BLOCK_KEYWORDS}
    assert "end" in {ln for ln in lines}
    assert block_openers, "expected at least one recognized block opener"
    # Nothing emitted as a leading token should be unknown to both sets.
    unknown = openers - highlight.BLOCK_KEYWORDS - highlight.COMMAND_KEYWORDS
    assert not unknown, f"emitter produces keywords the highlighter does not know: {sorted(unknown)}"


# --- second review pass: defects found in the follow-up rework ------------------


def test_sound_zero_location_update_rate_does_not_crash():
    from effdir_editor.model.components import default_sound

    r = default_resource()
    r.components.sounds.items.append(dataclasses.replace(default_sound(), location_update_rate=make_raw_f32(0.0)))
    child = dataclasses.replace(default_description_record(), name=WireString.from_text("s"), component_type=make_raw_u8(7), description_index=make_raw_u32(0))
    eff = dataclasses.replace(default_effect_description(), descriptions=WireVector(count=1, items=[child], source_span=None))
    r.effect_descriptions.items.append(eff)
    r.effect_name_map.items.append(StringU32Pair(name=WireString.from_text("E"), target=make_raw_u32(0)))
    result = emit_resource(r)  # previously raised ZeroDivisionError
    assert any("location_update_rate" in n.path for n in result.coverage.notes)


def test_camera_params_non_expandable_zoom_vector_is_reported_not_misspelled():
    from effdir_editor.model.resource import TrailingFloatMetadata

    r = default_resource()
    r.trailing_float_metadata = TrailingFloatMetadata(
        present=make_raw_u8(1),
        marker=make_raw_u16(0),
        count=make_raw_u32(5),
        values=(100.0, 50.0, 77.0, 12.0, 3.0, 100.0, 1.0, 4.0, 7.0),
    )
    result = emit_resource(r)
    # Previously emitted `camera 100 50 77 12 3`, five positional zoom
    # values, even though the command only accepts one (the parser expands
    # it to five by halving) -- a value that would either fail to parse or
    # silently re-expand into the wrong zoom levels on recompile.
    assert "camera" not in result.text
    assert any("trailing_float_metadata" in n.path and "not the single-value" in n.message for n in result.coverage.notes)


def test_camera_params_single_value_expansion_still_works():
    from effdir_editor.model.resource import TrailingFloatMetadata

    r = default_resource()
    r.trailing_float_metadata = TrailingFloatMetadata(
        present=make_raw_u8(1),
        marker=make_raw_u16(0),
        count=make_raw_u32(5),
        values=(100.0, 50.0, 25.0, 12.5, 6.25, 100.0, 1.0, 4.0, 7.0),
    )
    result = emit_resource(r)
    assert "camera 100" in result.text


def test_matrix_rotation_round_trip_including_gimbal_lock():
    import math

    from effdir_editor.fx.effects import _matrix_to_xyz_degrees
    from effdir_editor.model.effect import Matrix3

    def make_matrix(xd, yd, zd):
        x, y, z = math.radians(xd), math.radians(yd), math.radians(zd)
        sx, cx, sy, cy, sz, cz = math.sin(x), math.cos(x), math.sin(y), math.cos(y), math.sin(z), math.cos(z)
        rows = (
            (cy * cz, -cy * sz, sy),
            (sx * sy * cz + cx * sz, -sx * sy * sz + cx * cz, -sx * cy),
            (-cx * sy * cz + sx * sz, cx * sy * sz + sx * cz, cx * cy),
        )
        return Matrix3(row_0=Vec3(*rows[0]), row_1=Vec3(*rows[1]), row_2=Vec3(*rows[2]))

    for angles in [(30, 20, 10), (0, 90, 0), (45, 0, 0), (0, 0, 45), (170, 80, -170), (0, 0, 0)]:
        recovered = _matrix_to_xyz_degrees(make_matrix(*angles))
        assert recovered is not None
        # Re-build from the recovered angles and confirm it reproduces the
        # same matrix (gimbal lock can give a different but equivalent
        # angle triple, so compare matrices, not angles).
        rebuilt = make_matrix(*recovered)
        for a, b in zip(
            (rebuilt.row_0, rebuilt.row_1, rebuilt.row_2),
            (make_matrix(*angles).row_0, make_matrix(*angles).row_1, make_matrix(*angles).row_2),
        ):
            assert abs(a.x - b.x) < 1e-6 and abs(a.y - b.y) < 1e-6 and abs(a.z - b.z) < 1e-6
