"""Low-level `.fx` text formatting helpers.

Nothing here knows about the EFFDIR wire model or the binding catalog --
it only knows how to print numbers, vectors, quoted samples, and
`header ... end` blocks the way `docs/syntax/` and `docs/reference/`
describe the recovered fx surface. Keeping this separate from the
per-record emitters (particles.py, effects.py, ...) means every emitted
number goes through one place, so formatting stays consistent and is
easy to fix in one spot.

Quoting policy (see docs/reference/particles/appearance.md,
docs/reference/top-level/light.md, docs/reference/particles/force.md):
fixed-arity vec3 options (`-offset`, `emit -dir`, `randomWalk -preferDir`,
...) are written as three bare tokens; a vec3 that is one *sample* inside
a variable-length curve (`color`, `force -tractor`) is quoted as a single
string so the parser does not read its three components as three
separate curve samples.
"""

from __future__ import annotations

import math
import textwrap
from typing import Iterable, List, Sequence

from ..wire import Vec2, Vec3

_COMMENT_WRAP_WIDTH = 100


def is_emittable_float(value: float) -> bool:
    """False for NaN and +/-infinity. The wire format can hold these (the
    editor's own validation.py reports "non-finite floats" as a real
    diagnostic class), but there is no fx literal for them -- callers must
    record a coverage note rather than emit a silently wrong number."""

    return math.isfinite(value)


def fmt_num(value: float) -> str:
    """Render a float the way a human would type it, not the way struct
    unpacked it. `round(..., 6)` absorbs float32-round-trip noise (e.g.
    ``0.30000001192092896``) without inventing precision the wire value
    never had.

    Non-finite input degrades to ``0`` so a single corrupt float cannot
    abort a whole export, but it is the caller's job to have checked
    `is_emittable_float` first and noted the substitution; reaching this
    path silently would misrepresent the data.
    """

    if not isinstance(value, (int, float)):
        # Nearly every scalar in the model is a `Raw[float]` wrapper, so
        # passing the wrapper instead of `.value` is the easy mistake to
        # make here. Say so explicitly rather than failing later inside
        # math/format with a message that does not name the caller's bug.
        raise TypeError(f"fmt_num expects a plain float, got {type(value).__name__}; pass `.value` for a Raw wrapper")
    if not math.isfinite(value):
        return "0"
    rounded = round(float(value), 6)
    if rounded == 0.0:
        rounded = 0.0  # normalize -0.0
    if rounded == int(rounded) and abs(rounded) < 1e15:
        return str(int(rounded))
    text = f"{rounded:.6f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"


def fmt_int(value: int) -> str:
    return str(int(value))


def fmt_hex(value: int) -> str:
    """`resource-binding.md`: numeric fields accept lowercase `0x...` hex.
    Used for resource keys (texture/model/sound IDs) so the emitted file
    stays readable without claiming a symbolic name we cannot recover."""

    return f"0x{int(value) & 0xFFFFFFFF:08x}"


def fmt_vec3(v: Vec3) -> str:
    """Three bare tokens: `x y z`. For fixed-arity vec3 options only."""

    return f"{fmt_num(v.x)} {fmt_num(v.y)} {fmt_num(v.z)}"


def fmt_vec2_pair(v: Vec2) -> str:
    """Two bare tokens: `x y`. For fixed-arity min/max ranges."""

    return f"{fmt_num(v.x)} {fmt_num(v.y)}"


def fmt_vec2_sample(v: Vec2) -> str:
    """One quoted vec2 consumed as a single parser argument."""

    return f'"{fmt_num(v.x)} {fmt_num(v.y)}"'


def fmt_color_sample(v: Vec3) -> str:
    """One quoted curve sample: `"r g b"` (docs/reference/top-level/light.md,
    "Important grouping rule")."""

    return f'"{fmt_num(v.x)} {fmt_num(v.y)} {fmt_num(v.z)}"'


def fmt_vec3_sample(v: Vec3) -> str:
    """One quoted vec3 sample inside a variable-arity argument list, e.g.
    `force -tractor "0 0 0" ...` (docs/reference/particles/force.md)."""

    return f'"{fmt_num(v.x)} {fmt_num(v.y)} {fmt_num(v.z)}"'


def fmt_float_curve(values: Sequence[float]) -> str:
    return " ".join(fmt_num(v) for v in values)


def fmt_color_curve(values: Sequence[Vec3]) -> str:
    return " ".join(fmt_color_sample(v) for v in values)


def quote_name(name: str) -> str:
    """Names are normally bare identifiers; quote only if a raw name would
    not otherwise round-trip through the tokenizer (embedded whitespace).
    This is a display safeguard, not evidence of a quoting rule -- no fx
    doc page specifies name-quoting syntax."""

    if name == "" or any(ch.isspace() for ch in name):
        return f'"{name}"'
    return name


class FxWriter:
    """Accumulates indented `.fx` source lines."""

    def __init__(self, indent_unit: str = "    ") -> None:
        self._lines: List[str] = []
        self._indent = 0
        self._unit = indent_unit

    def blank(self) -> None:
        self._lines.append("")

    def line(self, text: str) -> None:
        if text == "":
            self.blank()
            return
        self._lines.append(f"{self._unit * self._indent}{text}")

    def lines(self, texts: Iterable[str]) -> None:
        for text in texts:
            self.line(text)

    def comment(self, text: str) -> None:
        """`docs/syntax/comments.md`: the only confirmed comment form is
        the block form `#< ... #>`. Long text (the export disclaimer) is
        wrapped across several short `#< ... #>` lines instead of one very
        long one -- every other emitted line is short, so a single long
        comment line forces a wide horizontal scrollbar the rest of the
        text never needs."""

        for chunk in textwrap.wrap(text, width=_COMMENT_WRAP_WIDTH) or [text]:
            self.line(f"#< {chunk} #>")

    def begin(self, header: str) -> None:
        self.line(header)
        self._indent += 1

    def end(self) -> None:
        self._indent = max(0, self._indent - 1)
        self.line("end")

    def multiline_command(self, parts: Sequence[str]) -> None:
        """Print a single logical command whose switches are pretty-printed
        across several indented lines (no `end`: this is one command, not a
        block -- see `docs/reference/effect-children/brush-effect.md`'s
        syntax block, which has no closing `end`)."""

        if not parts:
            return
        self.line(parts[0])
        self._indent += 1
        for part in parts[1:]:
            self.line(part)
        self._indent -= 1

    def text(self) -> str:
        return "\n".join(self._lines).rstrip("\n") + "\n"

    def __len__(self) -> int:
        return len(self._lines)
