"""Low-level `.fx` text formatting helpers.

Nothing here knows about the EFFDIR wire model or the binding catalog --
it only knows how to print numbers, vectors, quoted samples, and
`header ... end` blocks the way `docs/syntax/` and `docs/reference/`
describe the recovered fx surface. Keeping this separate from the
per-record emitters (particles.py, effects.py, ...) means every emitted
number goes through one place, so formatting stays consistent and is
easy to fix in one spot.

Quoting policy: **every vector is one quoted argument**. The parser splits
a line into arguments first and then hands one argument string to
`nSCRes::ParseVector2`/`ParseVector3`, which reads all of its components
out of that single string -- confirmed in the decal texture
(`0x00785890`), force (`0x0078710c`), emit (`0x0078667c`), randomWalk
(`0x0077fc62`), and shared child-option (`0x00401d2c`) parsers. Three bare
tokens are three arguments, not one vector.

`fmt_vec2_pair` is the exception and is not a vector: it prints two
genuinely separate float arguments (`life <a> <b>`, `randomWalk -delay
<base> <vary>`, ...), each of which the parser reads with its own
`ParseFloat`.
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


def fmt_asset_name(keyword: str, key: int) -> str:
    """Symbolic name for a texture/model resource key.

    `texture` and `model` do not accept a numeric key: they resolve a
    symbolic name through the parser's `textureID`/`modelID` map and throw
    `No such texture/model: '%s'` for anything not in it
    (docs/reference/particles/rendering.md,
    docs/reference/top-level/dynamic-particle.md). EFFDIR stores only the
    key, so the decompiler synthesizes one deterministic alias per key and
    declares it up front -- the same treatment brush/sound keys already get
    through `brushID`/`soundID`.
    """

    prefix = {"textureID": "tex", "modelID": "mdl"}[keyword]
    return f"{prefix}_{int(key) & 0xFFFFFFFF:08x}"


def fmt_vec2_pair(v: Vec2) -> str:
    """Two bare tokens: `x y`. Two separate float arguments, not a vector."""

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
        self._pending: List[str] | None = None

    def blank(self) -> None:
        self._lines.append("")

    def line(self, text: str) -> None:
        if self._pending is not None:
            self._pending.append(text)
            return
        if text == "":
            self.blank()
            return
        self._lines.append(f"{self._unit * self._indent}{text}")

    def lines(self, texts: Iterable[str]) -> None:
        for text in texts:
            self.line(text)

    def comment(self, text: str) -> None:
        """Emit a comment as `#<`, body lines, `#>` -- each on its own line.

        `#<` and `#>` must never share a line. `nSCRes::cFileParser::
        DoParseFile` (Mac `0x0041db38`) scans each line for `#<` and, on a
        hit, erases from there to end of line *before* looking for `#>`. A
        one-line `#< text #>` therefore destroys its own terminator, the
        parser latches into comment mode, and every remaining line of the
        file is swallowed -- the file silently never loads. Only a `#>` on a
        line that has no earlier `#<` closes the comment.
        """

        self.line("#<")
        for chunk in textwrap.wrap(text, width=_COMMENT_WRAP_WIDTH) or [text]:
            self.line(chunk)
        self.line("#>")

    def begin(self, header: str) -> None:
        self.line(header)
        self._indent += 1

    def end(self) -> None:
        self._indent = max(0, self._indent - 1)
        self.line("end")

    def command(self, parts: Sequence[str]) -> None:
        """Print one logical command: header plus switches, on one line.

        A command is not a block. Only the seven top-level definitions and
        the nested effect children are opened by a command and closed with
        `end` (docs/syntax/blocks-and-scopes.md); `force`, `warp`,
        `randomWalk`, `collision`, `model`, `brushEffect` and friends take
        switches instead, and their doc syntax blocks have no closing `end`.
        Spreading those switches over indented continuation lines is not a
        documented form either, so everything goes on the command's own line,
        which is the one spelling every syntax page shows.
        """

        if not parts:
            return
        self.line(" ".join(parts))

    # Older name, kept because several emitters still call it.
    multiline_command = command

    def begin_command(self, header: str) -> None:
        """Open a command whose switches are appended through `line()`, for
        emitters that build them across conditionals. `end_command` flushes
        the whole thing as the single line `command` would have written."""

        self._pending = [header]

    def end_command(self) -> None:
        parts, self._pending = self._pending or [], None
        self.line(" ".join(parts))

    def text(self) -> str:
        return "\n".join(self._lines).rstrip("\n") + "\n"

    def __len__(self) -> int:
        return len(self._lines)
