"""Tests for the .fx -> EFFDIR compiler.

The vanilla round trip needs the game's `SimCity_1.dat` and is skipped when
that file is absent. The rest compile small sources and read the bytes back.
"""

from __future__ import annotations

import os

import pytest

from effdir_editor.container.dbpf import DbpfArchive, Tgi
from effdir_editor.fx import emit_resource
from effdir_editor.fx.compile_cli import main as compile_main
from effdir_editor.fx.compiler import compile_source, compile_to_bytes
from effdir_editor.fx.parser import FxError, evaluate, parse_file
from effdir_editor.model.resource import read_resource, write_resource
from effdir_editor.wire import make_raw_u32

VANILLA = r"C:\Program Files (x86)\GOG Galaxy\Games\SimCity 4 Deluxe Edition\SimCity_1.dat"
VANILLA_TGI = Tgi(0xEA5118B0, 0xEA5118B1, 0x00000001)

SOURCE = """
textureID ring_tex 0x12345678
modelID ring_mdl 0x87654321

particles model_particle
    life 0.5 0.1
    source -point
    model ring_mdl -noCullFaces
end

decal looping_ring
    life 2 -loop
    texture ring_tex -ring
    size 16
end

particles texture_particle
    life 1
    emit -rate 30 -speed 4 1
    texture ring_tex -draw additive
    color "1 0.5 0.25"
end

effect ring_preview -noAutoStop
    particleEffect model_particle
    decalEffect looping_ring -lod 2
    particleEffect texture_particle
end
"""


def test_hand_written_effect_compiles_and_decompiles_to_equivalent_text():
    resource = compile_source(SOURCE, file="ring.fx")
    assert len(resource.particles.items) == 2
    assert len(resource.decals.items) == 1
    assert resource.decals.items[0].repeat_mode.value == 1
    assert resource.decals.items[0].flags.value & (1 << 5)
    assert resource.particles.items[0].flags_2.value & 1
    assert resource.particles.items[0].life.x == pytest.approx(0.4, abs=1e-6)

    data = write_resource(resource)
    back = read_resource(data)
    assert back.preservation.original_payload is None
    assert write_resource(back) == data

    text = emit_resource(back).text
    assert "model mdl_87654321 -noCullFaces" in text
    assert "life 2 -loop" in text and "-ring" in text
    assert "effect ring_preview -noAutoStop" in text
    # Decompiling and recompiling is a fixed point for what the text carries.
    assert compile_to_bytes(text, file="again.fx") == data


def test_bad_input_reports_file_and_line():
    with pytest.raises(FxError, match=r"bad\.fx:3: .*Unknown command 'bogus'"):
        compile_source("particles p\n    life 1\n    bogus 1\nend\n", file="bad.fx")
    with pytest.raises(FxError, match=r"bad\.fx:1:.*missing its `end`|bad\.fx.*missing its `end`"):
        compile_source("effect e\n    visualEffect x\n", file="bad.fx")
    with pytest.raises(FxError, match=r"bad\.fx:3: found `end` without an open block"):
        compile_source("particles p\nend\nend\n", file="bad.fx")
    with pytest.raises(FxError, match=r"bad\.fx:2: .*Unknown visual effect"):
        compile_source("effect a\n    visualEffect missing\nend\n", file="bad.fx")
    with pytest.raises(FxError, match=r"Unexpected switch: -nope"):
        compile_source("particles p\n    life 1 -nope\nend\n", file="bad.fx")
    with pytest.raises(FxError, match=r"No such texture"):
        compile_source("decal d\n    texture missing\nend\n", file="bad.fx")
    with pytest.raises(FxError, match=r"Unknown command 'collision'"):
        compile_source("particles p\n    collision -sticky\nend\n", file="bad.fx")
    with pytest.raises(FxError, match=r"Can't nest effects"):
        compile_source("effect a\n    effect b\n    end\nend\n", file="bad.fx")


def test_tokens_quotes_brackets_comments():
    assert parse_file('a "b c" d\'e f\'g (h i) #tail\n')[0].args == ["b c", "de fg", "h i"]
    commands = parse_file("#<\nignored\n#> after\nx 1\n")
    assert [c.name for c in commands] == ["after", "x"]
    assert commands[1].line == 4
    # `#<` swallows everything after it on its line, so one line never closes.
    assert parse_file("#< a #>\nignored\n") == []


def test_numeric_expressions():
    assert evaluate("1 + 2 * 3") == 7.0
    assert evaluate("-(4 / 2)") == -2.0
    assert evaluate("0xFF") == 255.0
    assert evaluate("2 ^ 3 ^ 2") == 512.0
    assert evaluate("sqrt(9) + pi - pi") == 3.0


def test_macros_variables_namespaces_eval():
    source = """
textureID t 1
set texname t
setf alpha 0.25
namespace n
    setf rate 7
end
define make "name rate"
    particles %name
        texture $texname
        emit -rate %rate $n:rate
        alpha $alpha
    end
enddef
create make "first 3"
define dup "i count"
    decal d%i
        life %count
    end
enddef
arrayCreate dup 2
effect e
    eval "particleEffect first"
end
"""
    resource = compile_source(source)
    particle = resource.particles.items[0]
    assert particle.emit_curve.items == [3.0, 7.0]
    assert particle.alpha_curve.items == [0.25]
    assert len(resource.decals.items) == 2
    assert resource.decals.items[1].life.value == 2.0
    assert len(resource.effect_descriptions.items) == 1


def test_macro_errors_have_positions():
    with pytest.raises(FxError, match=r"Unknown definition"):
        compile_source('create nope "1"\n', file="m.fx")
    with pytest.raises(FxError, match=r"Unknown variable: 'missing'"):
        compile_source("set x $missing\n", file="m.fx")
    with pytest.raises(FxError, match=r"Unknown parameter"):
        compile_source('define d "a"\n  decal %b\n  end\nenddef\ncreate d "1"\n', file="m.fx")


def _child_revisions(resource, index):
    return [d.legacy_transform.revision.value for d in resource.effect_descriptions.items[index].descriptions.items]


def test_redefinition_counts_assignments_in_the_transform_revision():
    # cS3DTransform::operator= adds one, its copy constructor zeroes (Mac
    # 0x0062BA46, 0x0066039A), and a redefinition assigns over the old
    # children. The parser's own operation counter never reaches the file.
    once = "particles p\nend\neffect e\n    particleEffect p -offset \"1 0 0\" -scale 2\nend\n"
    assert _child_revisions(compile_source(once), 0) == [0]
    twice = once + "effect e\n    particleEffect p\nend\n"
    assert _child_revisions(compile_source(twice), 0) == [1]
    thrice = twice + "effect e\n    particleEffect p\nend\n"
    assert _child_revisions(compile_source(thrice), 0) == [2]
    # Growing past the old child count reallocates, so nothing was assigned.
    grown = "particles p\nend\neffect e\n    particleEffect p\nend\neffect e\n    particleEffect p\n    particleEffect p\nend\n"
    assert _child_revisions(compile_source(grown), 0) == [0, 0]


def test_effect_vector_growth_zeroes_child_revisions():
    # Effect vector capacity doubles from 1, so adding index 2 reallocates and
    # copy-constructs every earlier child.
    source = "particles p\nend\neffect a\n    particleEffect p\nend\neffect a\n    particleEffect p\nend\n"
    assert _child_revisions(compile_source(source), 0) == [1]
    grown = source + "effect b\nend\neffect c\nend\n"
    assert _child_revisions(compile_source(grown), 0) == [0]


def test_revision_round_trips_through_ghost_definitions():
    source = "particles p\nend\neffect a\n    particleEffect p\nend\neffect a\n    particleEffect p\nend\neffect b\n    particleEffect p\nend\n"
    resource = compile_source(source)
    assert _child_revisions(resource, 0) == [0]  # adding b doubled the vector and zeroed it
    resource.effect_descriptions.items[1].descriptions.items[0].legacy_transform.revision = make_raw_u32(1)
    text = emit_resource(resource).text
    assert text.count("effect b") == 2
    assert _child_revisions(compile_source(text), 1) == [1]


def test_normalization_rounds_every_step_in_single_precision():
    # Reached by a 24-bit x87 and not by a double-precision inverse: vanilla
    # particle 85 stores this center, which a `-dir` of 1.7 produces.
    from effdir_editor.fx.float32 import normalized
    from effdir_editor.wire import Vec3

    assert normalized(Vec3(0.0, 1.7000000476837158, 0.0), "zyx").y == 0.9999999403953552


def test_include_expands_files_and_reports_their_positions(tmp_path):
    (tmp_path / "defs.fx").write_text("#<\nnote\n#>\nparticles p\n    life 1\nend\n", encoding="utf-8")
    source = 'include "defs.fx"\neffect e\n    particleEffect p\nend\n'
    resource = compile_source(source, file="main.fx", include_dir=str(tmp_path))
    assert len(resource.particles.items) == 1
    assert len(resource.effect_descriptions.items) == 1

    (tmp_path / "bad.fx").write_text("particles q\n    bogus 1\nend\n", encoding="utf-8")
    with pytest.raises(FxError, match=r"bad\.fx:2: .*Unknown command 'bogus'"):
        compile_source("sinclude bad.fx\n", file="main.fx", include_dir=str(tmp_path))
    with pytest.raises(FxError, match=r"main\.fx:1: Couldn't open file 'gone.fx'"):
        compile_source("include gone.fx\n", file="main.fx", include_dir=str(tmp_path))
    with pytest.raises(FxError, match=r'"include" takes a single argument'):
        compile_source("include a b\n", file="main.fx", include_dir=str(tmp_path))


def test_redefining_an_effect_keeps_its_record_and_name_map_entry():
    source = """
effect a
end
effect a
end
"""
    resource = compile_source(source)
    assert len(resource.effect_descriptions.items) == 1
    assert [n.name.decoded for n in resource.effect_name_map.items] == ["a"]


def test_select_applies_the_game_rounding_quirk():
    # 0.5 rounds to 32768 and the last child loses the count of explicit
    # children (Mac 0x0077DA24): 32768 + ~1 = 32768 + 65534, modulo 2^16.
    source = "particles p\nend\neffect e\n    select\n        particleEffect p -prob 0.5\n    end\nend\n"
    resource = compile_source(source)
    assert resource.effect_descriptions.items[0].descriptions.items[0].probability.value == 32766


def test_cli_creates_and_appends_preserving_other_entries(tmp_path, capsys):
    source = tmp_path / "ring.fx"
    source.write_text(SOURCE, encoding="utf-8")
    package = tmp_path / "ring.dat"

    assert compile_main([str(source), "-o", str(package), "--instance", "0x7ABC0001"]) == 0
    assert "EA5118B0-EA5118B1-7ABC0001" in capsys.readouterr().out
    archive = DbpfArchive.open(str(package))
    data = archive.read_decompressed(Tgi(0xEA5118B0, 0xEA5118B1, 0x7ABC0001))
    assert data == compile_to_bytes(SOURCE, file="ring.fx")

    second = tmp_path / "other.fx"
    second.write_text("effect only\nend\n", encoding="utf-8")
    assert compile_main([str(second), "-o", str(package), "--instance", "0x7ABC0002"]) == 0
    archive = DbpfArchive.open(str(package))
    assert archive.read_decompressed(Tgi(0xEA5118B0, 0xEA5118B1, 0x7ABC0001)) == data
    assert archive.find(Tgi(0xEA5118B0, 0xEA5118B1, 0x7ABC0002)) is not None


def test_cli_reports_errors_with_location(tmp_path, capsys):
    source = tmp_path / "bad.fx"
    source.write_text("particles p\n  bogus\nend\n", encoding="utf-8")
    assert compile_main([str(source), "-o", str(tmp_path / "x.dat"), "--instance", "1"]) == 1
    assert "bad.fx:2:" in capsys.readouterr().err


def _record_bytes(vector, writer):
    from effdir_editor.wire import WriteCursor

    out = []
    for item in vector.items:
        cursor = WriteCursor()
        writer(cursor, item)
        out.append(cursor.getvalue())
    return out


@pytest.mark.skipif(not os.path.exists(VANILLA), reason="SimCity_1.dat is not installed")
def test_vanilla_round_trip():
    from effdir_editor.model.common import ReadProfile, write_message_trigger, write_string_u32_pair, write_string_u32_u32_record
    from effdir_editor.model.components import write_attractor, write_brush, write_camera, write_scrubber, write_sequence, write_sound
    from effdir_editor.model.decal import write_decal
    from effdir_editor.model.dynamic_particle import write_dynamic_particle
    from effdir_editor.model.effect import write_effect_description
    from effdir_editor.model.light import write_light
    from effdir_editor.model.particle import write_particle
    from effdir_editor.model.shake import write_shake

    data = DbpfArchive.open(VANILLA).read_decompressed(VANILLA_TGI)
    vanilla = read_resource(data)
    compiled = compile_source(emit_resource(vanilla).text, file="vanilla.fx")

    collections = {
        "particles": (vanilla.particles, compiled.particles, write_particle),
        "decals": (vanilla.decals, compiled.decals, write_decal),
        "shakes": (vanilla.shakes, compiled.shakes, write_shake),
        "lights": (vanilla.lights, compiled.lights, write_light),
        "dynamic_particles": (vanilla.dynamic_particles, compiled.dynamic_particles, write_dynamic_particle),
        "brushes": (vanilla.components.brushes, compiled.components.brushes, write_brush),
        "attractors": (vanilla.components.attractors, compiled.components.attractors, write_attractor),
        "scrubbers": (vanilla.components.scrubbers, compiled.components.scrubbers, write_scrubber),
        "sequences": (vanilla.components.sequences, compiled.components.sequences, write_sequence),
        "sounds": (vanilla.components.sounds, compiled.components.sounds, write_sound),
        "cameras": (vanilla.components.cameras, compiled.components.cameras, write_camera),
        "effect_descriptions": (
            vanilla.effect_descriptions,
            compiled.effect_descriptions,
            lambda w, e: write_effect_description(w, e, ReadProfile.CURRENT),
        ),
        "effect_name_map": (vanilla.effect_name_map, compiled.effect_name_map, write_string_u32_pair),
        "effect_key_map": (vanilla.effect_key_map, compiled.effect_key_map, write_string_u32_u32_record),
        "message_triggers": (vanilla.message_triggers, compiled.message_triggers, write_message_trigger),
    }
    mismatches = {}
    for name, (expected, actual, writer) in collections.items():
        assert len(expected.items) == len(actual.items), name
        diff = [i for i, (a, b) in enumerate(zip(_record_bytes(expected, writer), _record_bytes(actual, writer))) if a != b]
        if diff:
            mismatches[name] = diff
    assert mismatches == {}
    assert write_resource(compiled) == data
