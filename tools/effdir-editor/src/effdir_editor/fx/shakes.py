"""EFFDIR `ShakeDescriptor` -> fx `shake NAME ... end`.

Mapping from `docs/reference/top-level/shake.md`."""

from __future__ import annotations

from ..model.shake import ShakeDescriptor
from .coverage import Coverage
from .writer import FxWriter, fmt_float_curve, fmt_num, quote_name

_BASE_TABLE_NAMES = {0: "random", 1: "sineY"}


def emit_shake(writer: FxWriter, coverage: Coverage, name: str, s: ShakeDescriptor, *, path: str) -> None:
    writer.begin(f"shake {quote_name(name)}")

    if s.length.value != 0.0 or s.fade.value != 0.0:
        line = f"length {fmt_num(s.length.value)}"
        if s.fade.value != 0.0:
            line += f" -fade {fmt_num(s.fade.value)}"
        writer.line(line)
    coverage.emitted()

    if s.amplitude.items:
        writer.line(f"amplitude {fmt_float_curve(s.amplitude.items)}")
    coverage.emitted()

    if s.frequency.items:
        writer.line(f"frequency {fmt_float_curve(s.frequency.items)}")
    coverage.emitted()

    if s.aspect.value != 0.0:
        writer.line(f"shakeAspect {fmt_num(s.aspect.value)}")
    coverage.emitted()

    table_name = _BASE_TABLE_NAMES.get(s.base_table.value)
    if table_name is not None and s.base_table.value != 0:
        writer.line(f"table {table_name}")
    elif s.base_table.value not in (0, 1):
        coverage.note(f"{path}.base_table", "unsupported", f"base_table={int(s.base_table.value)} is outside the two confirmed values (0=random, 1=sineY)")
    coverage.emitted()

    writer.end()
