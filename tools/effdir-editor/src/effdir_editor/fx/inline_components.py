"""The five "anonymous" effect-child component families: brush, attractor
(automata), scrubber, sound, camera. Unlike particle/decal/dynamicParticle/
sequence, these have no top-level pool syntax documented anywhere in
`docs/reference/top-level/` -- their full field values are written
directly on the child command itself
(`docs/reference/effect-children/{brush,scrubber,sound,camera,automata}-effect.md`).

Every function here returns a list of lines meant for
`FxWriter.multiline_command` -- these are all single logical commands
whose switches are pretty-printed across lines, not `header ... end`
blocks (none of their syntax examples have a closing `end`).

Brush and sound `-name` switches look up a numeric key in maps populated
by top-level `brushID`/`soundID` commands. They do not look up a previously
constructed component description, so each child command must carry its
own options.
"""

from __future__ import annotations

from typing import List

from ..model.components import AttractorDescription, BrushDescription, CameraDescription, ScrubberDescription, SoundDescription
from .bits import bit
from .coverage import Coverage
from .defaults import SOUND_DEFAULT
from .writer import fmt_num, fmt_vec2_pair, quote_name


def brush_effect_lines(name: str, b: BrushDescription, *, coverage: Coverage, path: str) -> List[str]:
    lines = [f"brushEffect -name {quote_name(name)}"]
    if b.mode.value != 0:
        lines.append(f"-apply {fmt_num(b.rate.value)}")
    elif b.rate.value != 0.0:
        lines.append(f"-rate {fmt_num(b.rate.value)}")
    if b.length.value != 0.0:
        lines.append(f"-length {fmt_num(b.length.value)}")
    if b.zoom.value != 0:
        lines.append(f"-zoom {int(b.zoom.value) + 1}")  # stored zero-based
    if b.strength.x != 0.0 or b.strength.y != 0.0:
        lines.append(f"-strength {fmt_vec2_pair(b.strength)}")
    if b.width.x != 0.0 or b.width.y != 0.0:
        lines.append(f"-width {fmt_vec2_pair(b.width)}")
    if b.level.value != 0.0:
        lines.append(f"-level {fmt_num(b.level.value)}")
    return lines


def automata_effect_lines(name: str, a: AttractorDescription, *, coverage: Coverage, path: str) -> List[str]:
    # selector: 0 = "-name" form, 1 = "-group" form (components.py docstring;
    # confirmed against real vanilla data, not just effdir.md's u32 guess).
    switch = "-group" if a.selector.value != 0 else "-name"
    return [f"automataEffect {switch} {quote_name(name)}"]


def scrubber_effect_lines(s: ScrubberDescription, *, coverage: Coverage, path: str) -> List[str]:
    flags = s.flags.value
    parts = []
    if bit(flags, 0):
        parts.append("-noNetworks")
    if bit(flags, 1):
        parts.append("-noFlora")
    if bit(flags, 2):
        parts.append("-dezone")
    if bit(flags, 3):
        parts.append("-single")
    if s.demolish.value != 0:
        parts.append(f"-demolish {fmt_num(s.demolish.value)}")
    if s.burn.value != 0:
        parts.append(f"-burn {fmt_num(s.burn.value)}")
    if s.min_size.value != 0.0:
        parts.append(f"-minDemolishSize {fmt_num(s.min_size.value)}")
    if s.max_size.value != 0.0:
        parts.append(f"-maxDemolishSize {fmt_num(s.max_size.value)}")
    if s.message_1.value != 0 or s.message_2.value != 0:
        parts.append(f"-message {int(s.message_1.value)} {int(s.message_2.value)}")
    if s.map_index.value != 0:
        # Both forms preserve map_value. Blob stores one half-extent in
        # both axes; unequal extents therefore prove the rect form.
        if s.map_half_extents.x == s.map_half_extents.y:
            shape = (
                f"-blob {int(s.map_index.value)} {fmt_num(s.map_value.value)} "
                f"{fmt_num(s.map_half_extents.x)}"
            )
        else:
            shape = (
                f"-rect {int(s.map_index.value)} {fmt_num(s.map_value.value)} "
                f"{fmt_num(s.map_half_extents.x)} {fmt_num(s.map_half_extents.y)}"
            )
        if s.map_spread.value != 0.0:
            shape += f" {fmt_num(s.map_spread.value)}"
        parts.append(shape)
    if bit(flags, 4):
        parts.append(f"-pauseSim {fmt_num(s.pause_duration.value)}" if s.pause_duration.value else "-pauseSim")
    if bit(flags, 5):
        parts.append(f"-pauseSimHidden {fmt_num(s.pause_duration.value)}" if s.pause_duration.value else "-pauseSimHidden")
    if bit(flags, 6):
        parts.append(f"-pauseClock {fmt_num(s.pause_duration.value)}" if s.pause_duration.value else "-pauseClock")
    if s.toxic is not None and s.toxic.value != 0:
        parts.append(f"-toxic {fmt_num(s.toxic.value)}")
    if s.extinguish_fire is not None and s.extinguish_fire.value != 0:
        parts.append(f"-extinguishFire {int(s.extinguish_fire.value)}")
    action = int(s.action.value)
    action_low = action & 0xFF
    action_kind = action & ~0xFF
    if action_kind == 0:
        if action_low != 1:
            parts.append(f"-demolishEffectID {action_low}")
    elif action_kind == 0x0300:
        parts.append("-createBurntRubble")
        if action_low != 1:
            parts.append(f"-demolishEffectID {action_low}")
    elif action_kind == 0x1300:
        if action_low == 2:
            parts.append("-explode")
        elif action_low == 1:
            parts.append("-createRubble")
        else:
            parts.append("-createRubble")
            parts.append(f"-demolishEffectID {action_low}")
    else:
        coverage.note(
            f"{path}.action",
            "unsupported",
            f"raw packed value 0x{action:08X} has unknown action-kind bits 0x{action_kind:08X}",
        )
    if s.value_10.value != 0:
        coverage.note(f"{path}.value_10", "unsupported", "no confirmed parser setter or runtime consumer")
    if not parts:
        coverage.note(path, "unsupported", "scrubberEffect requires at least one option; no recoverable option had a nonzero value")
        return []
    return ["scrubberEffect"] + parts


def sound_effect_lines(name: str, s: SoundDescription, *, coverage: Coverage, path: str) -> List[str]:
    lines = ["soundEffect", f"-name {quote_name(name)}"]
    rate = s.location_update_rate.value
    if rate != SOUND_DEFAULT.location_update_rate.value:
        if rate > 0.0:
            lines.append(f"-locationUpdateRate {fmt_num(1.0 / rate)}")
        else:
            # The parser only ever stores 1/x for a supplied x > 0, so a
            # zero (or negative) stored rate cannot come from that path --
            # most likely a hand-edited resource. 1.0/rate would raise
            # ZeroDivisionError; there is no source spelling to recover.
            coverage.note(
                f"{path}.location_update_rate",
                "unsupported",
                f"stored rate {rate!r} is not a positive reciprocal the -locationUpdateRate parser could have produced",
            )
    if s.length.value != 0.0:
        lines.append(f"-length {fmt_num(s.length.value)}")
    if s.flags.value != 0:
        coverage.note(f"{path}.flags", "unsupported", "bit 0 has no confirmed parser setter or runtime test")
    return lines


def camera_effect_lines(c: CameraDescription, *, coverage: Coverage, path: str) -> List[str]:
    flags = c.flags.value
    lines = []
    if bit(flags, 0):
        lines.append(f"-zoom {int(c.zoom.value) + 1}")  # stored zero-based
    if bit(flags, 1):
        lines.append(f"-rotation {int(c.rotation.value)}")
    if c.attach_radius.value != 0.0:
        lines.append(f"-attachRadius {fmt_num(c.attach_radius.value)}")
    if bit(flags, 2):
        lines.append("-target")
    if bit(flags, 3):
        lines.append("-slave")
    if not lines:
        return []
    return ["cameraEffect"] + lines
