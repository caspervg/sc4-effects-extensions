from effdir_editor.bindings.bitfields import bit_labels


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
