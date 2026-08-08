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
# see particle.py's module docstring. No catalog entries exist yet for the
# "second bitset" (flags_1), so it has no alias and falls back to "bit N"
# for every bit.
_MEMBER_ALIASES: Dict[Tuple[str, str], str] = {
    ("ParticleDescriptor", "flags_0"): "leading_bitset",
    ("ParticleDescriptor", "flags_2"): "third_bitset",
}

# Names established directly by the wire-model notes, even where the
# command catalog does not yet have one binding per bit. Unknown bits still
# deliberately fall back to ``bit N``.
_KNOWN_LABELS: Dict[Tuple[str, str], Dict[int, str]] = {
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
}


def bit_labels(record_type: str, attr_name: str, bit_count: int) -> List[str]:
    catalog_member = _MEMBER_ALIASES.get((record_type, attr_name), attr_name)
    by_bit: Dict[int, List[str]] = {}
    for binding in CATALOG:
        if binding.record_type != record_type:
            continue
        for bit_ref in binding.presence_bits:
            if bit_ref.member_path == catalog_member:
                by_bit.setdefault(bit_ref.bit, []).append(binding.command_path)
    known = _KNOWN_LABELS.get((record_type, attr_name), {})
    return [
        known[i] if i in known else ("/".join(by_bit[i]) if i in by_bit else f"bit {i}")
        for i in range(bit_count)
    ]
