"""EFFDIR `LightDescriptor` -> fx `light NAME ... end`.

Mapping from `docs/reference/top-level/light.md`. `length -fade <float>`
is deliberately never emitted: the doc notes the parser writes that
value into the shake working descriptor by mistake, so it is not part
of `cSC4LightDescription` and there is nothing here to recover it from.
"""

from __future__ import annotations

from ..model.light import LightDescriptor
from .coverage import Coverage
from .defaults import LIGHT_DEFAULT
from .writer import FxWriter, fmt_color_curve, fmt_float_curve, fmt_num, quote_name


def emit_light(writer: FxWriter, coverage: Coverage, name: str, l: LightDescriptor, *, path: str) -> None:
    writer.begin(f"light {quote_name(name)}")

    if l.strength.items:
        writer.line(f"strength {fmt_float_curve(l.strength.items)}")
    coverage.emitted()

    if l.length.value != LIGHT_DEFAULT.length.value:
        writer.line(f"length {fmt_num(l.length.value)}")
    coverage.emitted()

    if l.color.items:
        writer.line(f"color {fmt_color_curve(l.color.items)}")
    coverage.emitted()

    writer.end()
