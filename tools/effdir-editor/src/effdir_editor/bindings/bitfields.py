"""Per-bit labels for `bitset<N>` fields, derived from `catalog.py`'s
`BitRef` entries (`CommandBinding.presence_bits`). A bit with no catalog
coverage falls back to a plain `bit N` label -- catalog.py is deliberately
"a starter set, not the full table" (its own module docstring), so this
must degrade gracefully rather than assume full coverage.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .catalog import CATALOG

# ParticleDescriptor's three bitsets are named flags_0/flags_1/flags_2 in
# the model (particle.py), but catalog.py's BitRef entries were transcribed
# straight from effdir.md's doc names ("leading bitset"/"third bitset") --
# see particle.py's module docstring.
_MEMBER_ALIASES: Dict[Tuple[str, str], str] = {
    ("ParticleDescriptor", "flags_0"): "leading_bitset",
    ("ParticleDescriptor", "flags_1"): "second_bitset",
    ("ParticleDescriptor", "flags_2"): "third_bitset",
}

# Names established directly by the wire-model notes, even where the
# command catalog does not yet have one binding per bit. Unknown bits still
# deliberately fall back to ``bit N``.
_KNOWN_LABELS: Dict[Tuple[str, str], Dict[int, str]] = {
    # Mac SC4 text-parser writes at parser +0x120/+0x124/+0x128, anchored to
    # descriptor +0/+4/+8 by the constructor and binary reader/writer.  These
    # labels describe the source option that sets each bit; slash-separated
    # names are deliberate shared storage, not independent flags.
    ("ParticleDescriptor", "flags_0"): {
        0: "light",
        1: "inject",
        2: "maintain",
        3: "sustain",
        4: "noCull",
        5: "emit.base",
        6: "source.model",
        7: "source.modelBase",
        8: "collision",
        9: "collision.sticky",
        10: "terrainRepel",
        11: "killOutsideCity",
        12: "source.city",
        13: "source.cityWindySide",
        14: "source.pinToTerrain",
        15: "source.pinToWater",
        16: "source.heightFilter",
        17: "source.seaOnly",
        18: "source.lakeOnly",
        19: "emit.scale",
        20: "emit.areaScale",
        21: "emit.volumeScale",
        22: "source.scaleParticles",
        23: "randomWalk",
        24: "randomWalk.wait",
        25: "randomWalk.preferSea",
        26: "force.alphaAttractor",
        27: "force.motherDuck",
        28: "force.tractor",
        29: "texture.hflip",
        30: "texture.vflip",
        31: "timedEffect",
    },
    ("ParticleDescriptor", "flags_1"): {
        0: "collision.destroyBuildings",
        **{bit: f"bit {bit} (unused?)" for bit in range(1, 8)},
    },
    ("ParticleDescriptor", "flags_2"): {
        0: "model",
        1: "model.fakePerspective",
        2: "model.applyLighting",
        3: "model.moveEntireSlave",
        4: "model.applyAlpha/force.alphaAttractor",
        5: "model.sustain",
        6: "model.modelSpeed",
        7: "alignment.windBank",
        8: "warp.wiggleVerts/uv/alpha",
        9: "source.resetIncoming",
        10: "model.noCullFaces",
    },
    # No parser or runtime consumer was found for these bits, and all three
    # vanilla dynamic-particle descriptors store zero. Keep the uncertainty
    # explicit: they remain editable/preserved instead of being declared
    # definitively reserved.
    ("DynamicParticleDescriptor", "flags"): {
        bit: f"bit {bit} (unused?)" for bit in range(7)
    },
    ("DecalDescriptor", "flags"): {
        1: "light",
        2: "water",
        3: "repeat",
        4: "cityScale",
        5: "ring",
        6: "static",
    },
    ("ScrubberDescription", "flags"): {
        0: "noNetworks",
        1: "noFlora",
        2: "dezone",
        3: "single",
        4: "pauseSim",
        5: "pauseSimHidden",
        6: "pauseClock",
    },
    ("SequenceDescription", "flags"): {
        0: "loop",
        1: "noOverlap",
        2: "hardStart",
    },
    ("DescriptionRecord", "flags"): {
        0: "ignoreLength",
        1: "systemSequence",
    },
    # Group child commands construct EventRec entries directly: shakeEffect
    # sets bit 0, flashEffect sets bit 2, tintEffect sets bit 3, and their
    # epicentre/epicenter handling controls bit 1. StartAncilliary tests the
    # same bits before dispatching the referenced shake/light descriptor.
    ("EventRecord", "flags"): {
        0: "shakeEffect",
        1: "epicenter",
        2: "flashEffect",
        3: "tintEffect",
    },
    # The stream overload at 0x00768594 proves bitset<1>. The descriptor
    # constructor, parser, and all traced cSC4SoundEffect methods provide no
    # setter/test for it, so retain the qualified uncertainty in the editor.
    ("SoundDescription", "flags"): {
        0: "bit 0 (unused?)",
    },
    ("CameraDescription", "flags"): {
        0: "zoom",
        1: "rotation",
        2: "target",
        3: "slave",
    },
}


def bit_labels(record_type: str, attr_name: str, bit_count: int) -> List[str]:
    named = named_bits(record_type, attr_name, bit_count)
    return [named.get(i, f"bit {i}") for i in range(bit_count)]


def named_bits(record_type: str, attr_name: str, bit_count: int) -> Dict[int, str]:
    catalog_member = _MEMBER_ALIASES.get((record_type, attr_name), attr_name)
    by_bit: Dict[int, List[str]] = {}
    for binding in CATALOG:
        if binding.record_type != record_type:
            continue
        for bit_ref in binding.presence_bits:
            if bit_ref.member_path == catalog_member:
                by_bit.setdefault(bit_ref.bit, []).append(binding.command_path)
    known = _KNOWN_LABELS.get((record_type, attr_name), {})
    return {
        bit: known[bit] if bit in known else "/".join(by_bit[bit])
        for bit in range(bit_count)
        if bit in known or bit in by_bit
    }
