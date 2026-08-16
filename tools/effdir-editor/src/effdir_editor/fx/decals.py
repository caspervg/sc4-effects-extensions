"""EFFDIR `DecalDescriptor` -> fx `decal NAME ... end`.

Mapping from `docs/reference/top-level/decal.md` (nested command names)
cross-referenced with `docs/reference/binary/effdir.md` ("Section 2 -
Decal Descriptions", including its decal-flag table) and
`bindings/catalog.py`'s decal entries for which flag bit belongs to
which field. The draw domain is shared with particle draw options.
"""

from __future__ import annotations

from ..model.decal import DecalDescriptor
from .bits import bit
from .coverage import Coverage
from .defaults import DECAL_DEFAULT
from .writer import FxWriter, fmt_color_curve, fmt_float_curve, fmt_hex, fmt_num, fmt_vec2_pair, quote_name


_DRAW_TYPES = {
    0: "decal",
    1: "decalInvertDepth",
    2: "decalIgnoreDepth",
    3: "depthDecal",
    4: "depthDecalMasked",
    5: "additive",
    6: "additiveIgnoreDepth",
    7: "modulate",
}


def emit_decal(writer: FxWriter, coverage: Coverage, name: str, d: DecalDescriptor, *, path: str) -> None:
    writer.begin(f"decal {quote_name(name)}")
    flags = d.flags.value

    if d.color.items != DECAL_DEFAULT.color.items:
        writer.line(f"color {fmt_color_curve(d.color.items)}")
    coverage.emitted()

    if d.alpha.items != DECAL_DEFAULT.alpha.items or d.alpha_vary.value != DECAL_DEFAULT.alpha_vary.value:
        line = "alpha"
        if d.alpha.items:
            line += " " + fmt_float_curve(d.alpha.items)
        if d.alpha_vary.value != DECAL_DEFAULT.alpha_vary.value:
            line += f" -vary {fmt_num(d.alpha_vary.value)}"
        writer.line(line)
    coverage.emitted()

    if d.size.items != DECAL_DEFAULT.size.items or d.size_vary.value != DECAL_DEFAULT.size_vary.value or bit(flags, 4):
        line = "size"
        if d.size.items:
            line += " " + fmt_float_curve(d.size.items)
        if d.size_vary.value != DECAL_DEFAULT.size_vary.value:
            line += f" -vary {fmt_num(d.size_vary.value)}"
        if bit(flags, 4):
            line += " -cityScale"
        writer.line(line)
    coverage.emitted()

    if d.aspect.items != DECAL_DEFAULT.aspect.items:
        writer.line(f"aspect {fmt_float_curve(d.aspect.items)}")
    coverage.emitted()

    if d.rotation.items != DECAL_DEFAULT.rotation.items or d.rotate_vary.value != DECAL_DEFAULT.rotate_vary.value:
        line = "rotate"
        if d.rotation.items:
            line += " " + fmt_float_curve(d.rotation.items)
        if d.rotate_vary.value != DECAL_DEFAULT.rotate_vary.value:
            line += f" -vary {fmt_num(d.rotate_vary.value)}"
        writer.line(line)
    coverage.emitted()

    if d.life.value != DECAL_DEFAULT.life.value or bit(flags, 6) or d.repeat_mode.value != DECAL_DEFAULT.repeat_mode.value:
        mode = int(d.repeat_mode.value)
        parts = [f"life {fmt_num(d.life.value)}"]
        if bit(flags, 6):
            parts.append("-static")
            if mode == 0:
                coverage.note(
                    f"{path}.repeat_mode",
                    "unsupported",
                    "static flag with stored repeat_mode=0 cannot be produced by the life parser (-static writes mode 1)",
                )
        if mode == 1 and not bit(flags, 6):
            parts.append("-loop")
        elif mode == 2:
            parts.append("-single")
        elif mode == 3:
            parts.append("-sustain")
        elif mode not in (0, 1):
            coverage.note(
                f"{path}.repeat_mode",
                "unsupported",
                f"repeat_mode={mode} is outside the parser's mode domain 0..3",
            )
        writer.line(" ".join(parts))
    coverage.emitted()

    if d.draw_mode.value != DECAL_DEFAULT.draw_mode.value:
        draw_name = _DRAW_TYPES.get(d.draw_mode.value)
        if draw_name is None:
            coverage.note(
                f"{path}.draw_mode",
                "unsupported",
                f"draw_mode={int(d.draw_mode.value)} is outside the confirmed enum range 0..7",
            )
        else:
            writer.line(f"draw {draw_name}")
    coverage.emitted()

    if d.texture_key.value != 0 or bit(flags, 1) or bit(flags, 2) or bit(flags, 3) or bit(flags, 5):
        parts = [f"texture {fmt_hex(d.texture_key.value)}"]
        if bit(flags, 1):
            parts.append("-light")
        if bit(flags, 2):
            parts.append("-water")
        if bit(flags, 3):
            parts.append(f"-repeat {fmt_num(d.texture_repeat.value)}")
        if bit(flags, 5):
            parts.append("-ring")
        if d.texture_offset.x != 0.0 or d.texture_offset.y != 0.0:
            parts.append(f"-offset {fmt_vec2_pair(d.texture_offset)}")
        writer.line(" ".join(parts))
    coverage.emitted()

    if bit(flags, 0):
        coverage.note(f"{path}.flags", "unsupported", "flag bit 0 is not tested by core decal runtime code and has no confirmed fx spelling")

    writer.end()
