from effdir_editor.bindings.bitfields import bit_labels, named_bits


def test_particle_bitsets_use_mac_parser_and_runtime_names():
    assert bit_labels("ParticleDescriptor", "flags_0", 32) == [
        "light", "emit/inject", "maintain", "sustain", "noCull", "emit.base",
        "source.model", "source.modelBase", "collision", "collision.sticky",
        "terrainRepel", "killOutsideCity", "source.city", "source.cityWindySide",
        "source.pinToTerrain", "source.pinToWater", "source.heightFilter",
        "source.seaOnly", "source.lakeOnly", "emit.scale", "emit.areaScale",
        "emit.volumeScale", "source.scaleParticles", "randomWalk",
        "randomWalk.wait", "randomWalk.preferSea", "force.alphaAttractor",
        "force.motherDuck", "force.tractor", "texture.hflip", "texture.vflip",
        "timedEffect",
    ]
    assert bit_labels("ParticleDescriptor", "flags_1", 8) == [
        "collision.destroyBuildings",
        "bit 1 (unused?)", "bit 2 (unused?)", "bit 3 (unused?)",
        "bit 4 (unused?)", "bit 5 (unused?)", "bit 6 (unused?)",
        "bit 7 (unused?)",
    ]
    assert bit_labels("ParticleDescriptor", "flags_2", 11) == [
        "model", "model.fakePerspective", "model.applyLighting",
        "model.moveEntireSlave", "model.applyAlpha/force.alphaAttractor",
        "model.sustain", "model.modelSpeed", "alignment.windBank",
        "warp.wiggleVerts/uv/alpha", "source.resetIncoming",
        "model.noCullFaces",
    ]


def test_dynamic_particle_bitset_marks_unconsumed_bits_as_uncertain():
    assert bit_labels("DynamicParticleDescriptor", "flags", 7) == [
        "bit 0 (unused?)",
        "bit 1 (unused?)",
        "bit 2 (unused?)",
        "bit 3 (unused?)",
        "bit 4 (unused?)",
        "bit 5 (unused?)",
        "bit 6 (unused?)",
    ]


def test_decal_bitset_uses_confirmed_flag_names():
    assert bit_labels("DecalDescriptor", "flags", 7) == [
        "bit 0",
        "light",
        "water",
        "repeat",
        "cityScale",
        "ring",
        "static",
    ]
    assert 0 not in named_bits("DecalDescriptor", "flags", 7)


def test_scrubber_bitset_uses_confirmed_flag_names():
    assert bit_labels("ScrubberDescription", "flags", 7) == [
        "noNetworks",
        "noFlora",
        "dezone",
        "single",
        "pauseSim",
        "pauseSimHidden",
        "pauseClock",
    ]


def test_sequence_bitset_uses_confirmed_option_names():
    assert bit_labels("SequenceDescription", "flags", 3) == [
        "loop",
        "noOverlap",
        "hardStart",
    ]


def test_sound_and_camera_bitsets_use_traced_labels():
    assert bit_labels("SoundDescription", "flags", 1) == ["bit 0 (unused?)"]
    assert bit_labels("CameraDescription", "flags", 4) == [
        "zoom",
        "rotation",
        "target",
        "slave",
    ]


def test_description_record_bits_use_parser_and_runtime_names():
    assert bit_labels("DescriptionRecord", "flags", 2) == [
        "ignoreLength",
        "systemSequence",
    ]


def test_event_record_bits_use_group_command_and_runtime_names():
    assert bit_labels("EventRecord", "flags", 4) == [
        "shakeEffect",
        "epicenter",
        "flashEffect",
        "tintEffect",
    ]
