"""EFFDIR `SequenceDescription` (Section 8, component_type 6) -> fx
top-level `sequenceEffect NAME ... end`.

Mapping from `docs/reference/top-level/sequence.md`. A `SequenceItem`
with an empty `effect_name` is a `wait`; a non-empty one is a `play`
(`effdir.md`, "Section 8 - Sequence Descriptions": "A wait item has an
empty effect name.").
"""

from __future__ import annotations

from ..model.components import SequenceDescription
from .bits import bit
from .coverage import Coverage
from .writer import FxWriter, fmt_num, quote_name


def emit_sequence(writer: FxWriter, coverage: Coverage, name: str, s: SequenceDescription, *, path: str) -> None:
    switches = []
    flags = s.flags.value
    if bit(flags, 0):
        switches.append("-loop")
    if bit(flags, 1):
        switches.append("-noOverlap")
    if bit(flags, 2):
        switches.append("-hardStart")
    header = f"sequenceEffect {quote_name(name)}" + ("".join(f" {s}" for s in switches))
    writer.begin(header)

    for item in s.items.items:
        effect_name = item.effect_name.decoded or ""
        a = fmt_num(item.timing.x)
        b = fmt_num(item.timing.y)
        if effect_name:
            writer.line(f"play {quote_name(effect_name)} {a} {b}")
        else:
            writer.line(f"wait {a} {b}")
    coverage.emitted()

    writer.end()
