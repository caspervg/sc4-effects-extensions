from effdir_editor.bindings.bitfields import bit_labels


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
