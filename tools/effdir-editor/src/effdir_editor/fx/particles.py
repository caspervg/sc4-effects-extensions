"""EFFDIR `ParticleDescriptor` -> fx `particles NAME ... end`.

Field-to-command mapping follows `docs/reference/binary/effdir.md`
("Particle records: direct command assignments", "Behavior 1/2/3 Bits")
and the per-subcommand pages under `docs/reference/particles/`. Every
place the wire format cannot distinguish between two or more fx
spellings (they write the same storage, or a shared flag bit covers more
than one option) is called out in a comment and reported through
`Coverage` rather than guessed -- see the module docstring pattern used
throughout `docs/reference/binary/effdir.md` itself
("Confirmed"/"Partial"/"Inferred").
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from ..model.particle import ParticleDescriptor
from ..wire import Bounds3, Vec2, Vec3
from .float32 import bits, f32, fit_base_vary, fit_unit, nearby_singles, normalized
from .bits import bit
from .coverage import Coverage
from .defaults import PARTICLE_DEFAULT
from .writer import FxWriter, fmt_asset_name, fmt_color_curve, fmt_float_curve, fmt_hex, fmt_num, fmt_scaled, fmt_vec2_pair, fmt_vec2_sample, fmt_vec3_sample, quote_name


_PARTICLE_DRAW_TYPES = {
    0: "decal",
    1: "decalInvertDepth",
    2: "decalIgnoreDepth",
    3: "depthDecal",
    4: "depthDecalMasked",
    5: "additive",
    6: "additiveIgnoreDepth",
    7: "modulate",
}

_ALIGN_TYPES = {0: "camera", 1: "ground", 2: "dirX", 3: "dirY", 4: "dirZ"}

# cParticleSourceCommand initializes this local box before applying shape
# switches. It differs from the particle descriptor constructor's 3-D box.
_SOURCE_COMMAND_DEFAULT_BOUNDS = Bounds3(Vec3(-1.0, 0.0, -1.0), Vec3(1.0, 0.0, 1.0))
_ZERO_BOUNDS = Bounds3(Vec3(0.0, 0.0, 0.0), Vec3(0.0, 0.0, 0.0))

def _nz2(v: Vec2) -> bool:
    return v.x != 0.0 or v.y != 0.0


def _nz3(v: Vec3) -> bool:
    return v.x != 0.0 or v.y != 0.0 or v.z != 0.0


def emit_particles(writer: FxWriter, coverage: Coverage, name: str, p: ParticleDescriptor, *, path: str) -> None:
    writer.begin(f"particles {quote_name(name)}")

    flags0 = p.flags_0.value
    flags1 = p.flags_1.value
    flags2 = p.flags_2.value

    _emit_life(writer, coverage, p, path)
    _emit_emission(writer, coverage, p, flags0, path)
    _emit_source(writer, coverage, p, flags0, flags2, path)
    _emit_force(writer, coverage, p, flags0, path)
    _emit_terrain_repel(writer, coverage, p, flags0, path)
    _emit_warp(writer, coverage, p, flags2, path)
    _emit_random_walk(writer, coverage, p, flags0, path)
    _emit_collision(writer, coverage, p, flags0, flags1, path)
    _emit_appearance(writer, coverage, p, path)
    _emit_texture_model_align(writer, coverage, p, flags0, flags2, path)
    _emit_timed_effects(writer, coverage, p, path)
    _report_unrepresentable(coverage, p, path)

    writer.end()


def _report_unrepresentable(coverage: Coverage, p: ParticleDescriptor, path: str) -> None:
    """Fields the wire format stores but no recovered fx command writes.

    effdir.md marks each of these "**Unknown.** We did not find a parser
    setter or runtime reader" -- there is no fx spelling to emit, so the
    only honest handling is to say so rather than drop them silently.
    Constructor defaults (value_166=1, value_168=1.0, per
    model/particle.py's `default_particle`) are not reported: they carry
    no authored information.
    """

    if p.value_164.value != 0:
        coverage.skipped(f"{path}.value_164", f"unknown field holds {int(p.value_164.value)}; no fx spelling to emit")
    if p.value_166.value != 1:
        coverage.skipped(f"{path}.value_166", f"unknown field holds {int(p.value_166.value)} (constructor default is 1); no fx spelling to emit")
    if p.value_168.value != 1.0:
        coverage.skipped(f"{path}.value_168", f"unknown field holds {p.value_168.value!r} (constructor default is 1.0); no fx spelling to emit")
    if p.flags_1.value & ~0b1:
        coverage.skipped(
            f"{path}.flags_1",
            f"bits 1-7 of the second bitset are set (raw {int(p.flags_1.value)}); only bit 0 (destroyBuildings) has a known spelling",
        )


def _emit_life(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, path: str) -> None:
    if p.life != PARTICLE_DEFAULT.life or p.preroll.value != PARTICLE_DEFAULT.preroll.value:
        # `life base [vary]` stores base-vary and base+vary, and an omitted
        # -preroll stores the base value (cParticleLifeCommand, Mac 0x0077E104).
        base, vary, exact = fit_base_vary(p.life.x, p.life.y)
        if not exact:
            coverage.note(f"{path}.life", "unsupported", "stored life bounds have no exact base-plus-variation spelling, the nearest was emitted")
        line = f"life {fmt_num(base)}"
        if vary != 0.0:
            line += f" {fmt_num(vary)}"
        if p.preroll.value != base:
            line += f" -preroll {fmt_num(p.preroll.value)}"
        writer.line(line)
    coverage.emitted()


def _emit_emission(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags0: int, path: str) -> None:
    has_curve = p.emit_curve.items != PARTICLE_DEFAULT.emit_curve.items
    is_maintain = bit(flags0, 2)
    is_inject = bit(flags0, 1)
    timing = _emission_shared_options(p, flags0)

    # Everything but -delay is emit-only: `maintain` takes no other switch
    # (cParticleMaintainCommand, Mac 0x00785E28), so the shared options ride
    # on a separate `emit` line.
    value = p.emit_curve.items[0] if p.emit_curve.items else 0.0
    if is_maintain:
        if is_inject:
            writer.line(f"emit -inject {fmt_num(value)}")
        line = f"maintain {fmt_num(value)}"
        if p.emit_delay != PARTICLE_DEFAULT.emit_delay:
            line += f" -delay {fmt_vec2_pair(p.emit_delay)}"
        writer.line(line)
        timing = [t for t in timing if not t.startswith("-delay ")]
        if len(p.emit_curve.items) > 1:
            coverage.note(
                f"{path}.emit_curve",
                "info",
                f"maintain takes a single value but {len(p.emit_curve.items)} curve samples are stored, only the first was emitted",
            )
        rate_parts: List[str] = []
    elif is_inject:
        rate_parts = [f"-inject {fmt_num(value)}"]
        if len(p.emit_curve.items) > 1:
            coverage.note(
                f"{path}.emit_curve",
                "unsupported",
                f"inject mode stores one value but {len(p.emit_curve.items)} curve samples are present, only the first can be emitted",
            )
    elif has_curve:
        rate_parts = [f"-rate {fmt_float_curve(p.emit_curve.items)}"]
    else:
        rate_parts = []

    motion = _emission_motion(coverage, p, flags0, path)
    if rate_parts or timing or motion:
        writer.line(" ".join(["emit", *rate_parts, *timing, *motion]))
    coverage.emitted()


def _emission_motion(coverage: Coverage, p: ParticleDescriptor, flags0: int, path: str) -> List[str]:
    """Velocity and speed. `-dir` writes the bounds and leaves speed alone,
    so it can carry the stored box exactly, while `-velocity` also rewrites
    speed (cParticleEmitCommand, Mac 0x0078667C)."""

    parts: List[str] = []
    bounds = p.emit_velocity_bounds
    if bounds != PARTICLE_DEFAULT.emit_velocity_bounds:
        spelling = _fit_direction(bounds)
        if spelling is None:
            coverage.note(
                f"{path}.emit_velocity_bounds",
                "unsupported",
                f"velocity bounds {bounds!r} have no `-dir` spelling that reproduces them exactly, "
                "the nearest spelling was emitted",
            )
            center = Vec3((bounds.minimum.x + bounds.maximum.x) / 2, (bounds.minimum.y + bounds.maximum.y) / 2, (bounds.minimum.z + bounds.maximum.z) / 2)
            half = Vec3((bounds.maximum.x - bounds.minimum.x) / 2, (bounds.maximum.y - bounds.minimum.y) / 2, (bounds.maximum.z - bounds.minimum.z) / 2)
            spelling = (center, half if _nz3(half) else None)
        center, half = spelling
        parts.append(f"-dir {fmt_vec3_sample(center)}" + (f" {fmt_vec3_sample(half)}" if half is not None else ""))
    if p.emit_speed != PARTICLE_DEFAULT.emit_speed:
        base, vary, exact = fit_base_vary(p.emit_speed.x, p.emit_speed.y)
        if not exact:
            coverage.note(f"{path}.emit_speed", "unsupported", "stored speed range has no exact base-plus-variation spelling, the nearest was emitted")
        parts.append(f"-speed {fmt_num(base)}" + (f" {fmt_num(vary)}" if vary != 0.0 else ""))
    if bit(flags0, 5):
        parts.append("-base")
    return parts


def _fit_direction(bounds: Bounds3):
    """`-dir center [half]`: the parser normalizes center (when nonzero) and
    stores center minus and plus half. Returns exact singles or None."""

    def forward(center: Vec3, half: Vec3) -> Bounds3:
        if center.x * center.x + center.y * center.y + center.z * center.z > 0.0:
            center = normalized(center)
        return Bounds3(
            Vec3(f32(center.x - half.x), f32(center.y - half.y), f32(center.z - half.z)),
            Vec3(f32(center.x + half.x), f32(center.y + half.y), f32(center.z + half.z)),
        )

    mn, mx = bounds.minimum, bounds.maximum
    center = Vec3(f32((mn.x + mx.x) / 2.0), f32((mn.y + mx.y) / 2.0), f32((mn.z + mx.z) / 2.0))
    half = Vec3(f32((mx.x - mn.x) / 2.0), f32((mx.y - mn.y) / 2.0), f32((mx.z - mn.z) / 2.0))
    if forward(center, half) == bounds:
        return center, (half if _nz3(half) else None)
    unit = fit_unit(center)
    if unit is not None and forward(unit, half) == bounds:
        return unit, (half if _nz3(half) else None)
    # Stored values passed through a normalize, so search single-precision
    # neighbours of the implied center and half (axis-independent).
    def axis(cv, hv, lo, hi):
        for c in nearby_singles(cv, 8):
            for h in nearby_singles(hv, 8):
                if f32(c - h) == lo and f32(c + h) == hi:
                    return c, h
        return None
    fitted = [axis(center.x, half.x, mn.x, mx.x), axis(center.y, half.y, mn.y, mx.y), axis(center.z, half.z, mn.z, mx.z)]
    if not all(fitted):
        return None
    h = Vec3(fitted[0][1], fitted[1][1], fitted[2][1])
    target = Vec3(fitted[0][0], fitted[1][0], fitted[2][0])
    for x in nearby_singles(target.x, 2):
        for y in nearby_singles(target.y, 2):
            for z in nearby_singles(target.z, 2):
                if forward(Vec3(x, y, z), h) == bounds:
                    return Vec3(x, y, z), (h if _nz3(h) else None)
    unit = fit_unit(target)
    if unit is not None and forward(unit, h) == bounds:
        return unit, (h if _nz3(h) else None)
    return None


def _emission_shared_options(p: ParticleDescriptor, flags0: int) -> List[str]:
    parts: List[str] = []
    if p.emit_loop_count.value == 1 and p.emit_loop_interval.value != 0.0:
        parts.append(f"-single {fmt_num(p.emit_loop_interval.value)}")
    elif (
        p.emit_loop_interval.value != PARTICLE_DEFAULT.emit_loop_interval.value
        or p.emit_loop_count.value != PARTICLE_DEFAULT.emit_loop_count.value
    ):
        parts.append(f"-loop {fmt_num(p.emit_loop_interval.value)} {int(p.emit_loop_count.value)}")
    if bit(flags0, 3):
        parts.append("-sustain")
    if bit(flags0, 19):
        parts.append("-scale")
    if bit(flags0, 20):
        parts.append("-areaScale")
    if bit(flags0, 21):
        parts.append("-volumeScale")
    if p.emit_delay != PARTICLE_DEFAULT.emit_delay:
        parts.append(f"-delay {fmt_vec2_pair(p.emit_delay)}")
    if p.emit_trigger != PARTICLE_DEFAULT.emit_trigger:
        parts.append(f"-trigger {fmt_vec2_pair(p.emit_trigger)}")
    return parts


def _emit_source(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags0: int, flags2: int, path: str) -> None:
    bounds = p.source_bounds
    has_bounds = bounds != PARTICLE_DEFAULT.source_bounds
    has_dice = p.model_speed.value != PARTICLE_DEFAULT.model_speed.value
    has_filters = any(
        bit(flags0, n) for n in (6, 7, 12, 13, 14, 15, 16, 17, 18, 22)
    ) or bit(flags2, 9) or bit(flags0, 11)
    if not (has_bounds or has_dice or has_filters):
        coverage.emitted()
        return

    # The shape switches are an else-if chain (cParticleSourceCommand, Mac
    # 0x0077F0D6): -dice, -model, -modelBase, -city and -cityWindySide each
    # exclude a box, so the line can carry only one of them.
    shape: List[str] = []
    if has_dice:
        shape.append(f"-dice {fmt_num(p.model_speed.value)}")
        if bounds != _ZERO_BOUNDS:
            coverage.note(f"{path}.source_bounds", "unsupported", "-dice zeroes the bounds, so the stored nonzero bounds were dropped")
    elif bit(flags0, 13) or bit(flags0, 12):
        keyword = "-cityWindySide" if bit(flags0, 13) else "-city"
        low, high = bounds.minimum.y, bounds.maximum.y
        flat = bounds.minimum.x == -1.0 and bounds.minimum.z == -1.0 and bounds.maximum.x == 1.0 and bounds.maximum.z == 1.0
        if not flat:
            coverage.note(f"{path}.source_bounds", "unsupported", "city mode stores only a Y range, the stored X/Z extents were dropped")
        shape.append(f"{keyword} {fmt_num(low)} {fmt_num(high)}" if (low, high) != (0.0, 0.0) else keyword)
    elif bit(flags0, 6) or bit(flags0, 7):
        shape.append("-model" if bit(flags0, 6) else "-modelBase")
        if bounds != _SOURCE_COMMAND_DEFAULT_BOUNDS:
            coverage.note(f"{path}.source_bounds", "unsupported", "-model keeps the implicit flat box, so the stored bounds were dropped")
    elif not _bounds_identical(bounds, _SOURCE_COMMAND_DEFAULT_BOUNDS):
        spelling = _fit_source_shape(bounds)
        if spelling is None:
            coverage.note(f"{path}.source_bounds", "unsupported", f"source bounds {bounds!r} have no exact shape spelling, the nearest box was emitted")
            spelling = _nearest_box(bounds)
        shape.append(spelling)

    options = list(shape)
    if bit(flags0, 22):
        options.append("-scaleParticles")
    if bit(flags0, 14):
        options.append("-pinToTerrain")
    if bit(flags0, 15):
        options.append("-pinToWater")
    if bit(flags0, 16):
        # `-belowHeight`/`-aboveHeight`/`-heightRange` share one Vec2
        # (effdir.md "+0x158, source belowHeight/aboveHeight/heightRange").
        # The stored range alone cannot say which single-value spelling
        # was authored, so use the exact two-value canonical form.
        options.append(f"-heightRange {fmt_vec2_pair(p.height_range)}")
    if bit(flags0, 17):
        options.append("-seaOnly")
    if bit(flags0, 18):
        options.append("-lakeOnly")
    if bit(flags2, 9):
        options.append("-resetIncoming")
    if bit(flags0, 11):
        options.append("-killOutsideCity")

    writer.line(" ".join(["source", *options]))
    if bit(flags0, 6) and bit(flags0, 7):
        # A second `source` command is the only way to set both model bits:
        # the shape switches are exclusive on one line.
        writer.line("source -modelBase")
    coverage.emitted()


def _bounds_identical(a: Bounds3, b: Bounds3) -> bool:
    """Bit-exact, so a stored `-0.0` from a shape switch counts as different."""

    return all(
        bits(x) == bits(y)
        for x, y in zip(
            (a.minimum.x, a.minimum.y, a.minimum.z, a.maximum.x, a.maximum.y, a.maximum.z),
            (b.minimum.x, b.minimum.y, b.minimum.z, b.maximum.x, b.maximum.y, b.maximum.z),
        )
    )


def _shape_candidates(bounds: Bounds3):
    """Source-shape spellings for stored bounds. `-box` covers every centered
    shape including the `-0.0` a negated half leaves, `-point` stores plain
    zeros, and an explicit center runs the parser's translation, which
    turns a `-0.0` into `+0.0`."""

    half = Vec3(
        f32((bounds.maximum.x - bounds.minimum.x) / 2.0),
        f32((bounds.maximum.y - bounds.minimum.y) / 2.0),
        f32((bounds.maximum.z - bounds.minimum.z) / 2.0),
    )
    center = Vec3(
        f32((bounds.maximum.x + bounds.minimum.x) / 2.0),
        f32((bounds.maximum.y + bounds.minimum.y) / 2.0),
        f32((bounds.maximum.z + bounds.minimum.z) / 2.0),
    )
    box = f"-box {fmt_vec3_sample(half)}"
    if not _nz3(center):
        yield box, Vec3(-half.x, -half.y, -half.z), half, center, False
        yield "-point", Vec3(0.0, 0.0, 0.0), Vec3(0.0, 0.0, 0.0), center, False
    yield f"{box} {fmt_vec3_sample(center)}", Vec3(-half.x, -half.y, -half.z), half, center, True


def _fit_source_shape(bounds: Bounds3) -> Optional[str]:
    for text, minimum, maximum, center, applied in _shape_candidates(bounds):
        rebuilt = Bounds3(minimum, maximum)
        if applied:
            rebuilt = Bounds3(
                Vec3(f32(minimum.x + center.x), f32(minimum.y + center.y), f32(minimum.z + center.z)),
                Vec3(f32(maximum.x + center.x), f32(maximum.y + center.y), f32(maximum.z + center.z)),
            )
        if _bounds_identical(rebuilt, bounds):
            return text
    return None


def _nearest_box(bounds: Bounds3) -> str:
    return list(_shape_candidates(bounds))[-1][0]


def _emit_force(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags0: int, path: str) -> None:
    parts = []
    if p.force.x == 0.0 and p.force.z == 0.0 and p.force.y != 0.0:
        # -gravity adds (0, -g, 0) with no normalization, so it is exact.
        parts.append(f"-gravity {fmt_num(-p.force.y)}")
    elif _nz3(p.force):
        spelling = _fit_wind(p.force)
        if spelling is None:
            coverage.note(f"{path}.force", "unsupported", f"force {p.force!r} has no exact -wind spelling, the nearest was emitted")
            magnitude = math.sqrt(p.force.x * p.force.x + p.force.y * p.force.y + p.force.z * p.force.z)
            spelling = (Vec3(p.force.x / magnitude, p.force.y / magnitude, p.force.z / magnitude), magnitude)
        parts.append(f"-wind {fmt_vec3_sample(spelling[0])} {fmt_num(spelling[1])}")
    if p.global_wind.value != 0.0:
        parts.append(f"-global_wind {fmt_num(p.global_wind.value)}")
    if p.drag.value != 0.0:
        parts.append(f"-drag {fmt_num(p.drag.value)}")
    if p.screw.value != 0.0:
        # Both force's and warp's -screw store the value times 0.02.
        parts.append(f"-screw {fmt_scaled(p.screw.value, 0.02)}")
    if p.bomb.value != 0.0 or _nz3(p.bomb_direction):
        parts.append(f"-bomb {fmt_num(p.bomb.value)} {fmt_vec3_sample(p.bomb_direction)}")

    attractor_active = (
        p.attractor_curve.items != PARTICLE_DEFAULT.attractor_curve.items
        or p.attractor_strength.value != PARTICLE_DEFAULT.attractor_strength.value
        or p.automata_id.value != PARTICLE_DEFAULT.automata_id.value
        or bit(flags0, 26)
        or bit(flags0, 27)
    )
    if attractor_active:
        curve = fmt_float_curve(p.attractor_curve.items)
        if bit(flags0, 26):
            parts.append(f"-alphaAttractor {fmt_num(p.attractor_strength.value)} {curve}".rstrip())
        elif bit(flags0, 27):
            parts.append(f"-motherDuck {fmt_num(p.attractor_strength.value)} {curve}".rstrip())
        elif p.automata_id.value != 0:
            # The parser stores strength 1 and this argument as the single curve value.
            parts.append(f"-automata {int(p.automata_id.value)} {curve}".rstrip())
        else:
            parts.append(f"-attractor {fmt_num(p.attractor_strength.value)} {curve}".rstrip())

    tractor_lines: List[str] = []
    if len(p.tractor_points.items) > 0 or bit(flags0, 28):
        previous_end = 0.0
        for index, tp in enumerate(p.tractor_points.items):
            # Always written as an absolute point with an explicit tangent
            # vector: -tractorRel's chaining is resolved into the same
            # absolute-position storage before it reaches the wire, and
            # the wire never distinguishes an auto-derived tangent from an
            # explicitly authored one (force.md, "Second argument forms").
            # The force parser takes one -tractor per command (it never
            # loops), so each point needs its own line.
            line = f"force -tractor {fmt_vec3_sample(tp.position)} {fmt_vec3_sample(tp.direction)}"
            duration = f32(tp.amount.value - tp.time.value)
            if duration != 0.0:
                line += f" {fmt_num(duration)}"
            tractor_lines.append(line)
            if tp.time.value != previous_end:
                coverage.note(
                    f"{path}.tractor_points[{index}]",
                    "unsupported",
                    f"stored segment starts at {tp.time.value!r}, but parser chaining would start it at {previous_end!r}",
                )
            previous_end = tp.amount.value
        if p.tractor_reset_speed.value != 0.0:
            parts.append(f"-tractorResetSpeed {fmt_num(p.tractor_reset_speed.value)}")

    if (
        p.explosion.value != PARTICLE_DEFAULT.explosion.value
        or p.explosion_curve.items != PARTICLE_DEFAULT.explosion_curve.items
    ):
        curve = fmt_float_curve(p.explosion_curve.items)
        parts.append(f"-explosion {fmt_num(p.explosion.value)} {curve}".rstrip())
    if (
        p.explosion_front.value != PARTICLE_DEFAULT.explosion_front.value
        or p.explosion_front_secondary.value != PARTICLE_DEFAULT.explosion_front_secondary.value
    ):
        parts.append(f"-explosionFront {fmt_num(p.explosion_front.value)} {fmt_num(p.explosion_front_secondary.value)}")

    if parts:
        writer.begin_command("force")
        for part in parts:
            writer.line(part)
        writer.end_command()
    for line in tractor_lines:
        writer.line(line)
    coverage.emitted()


def _fit_wind(force: Vec3):
    """Direction and magnitude singles for which `-wind` reproduces `force`
    bit for bit (normalize, multiply, then add to zero)."""

    magnitude = f32(math.sqrt(force.x * force.x + force.y * force.y + force.z * force.z))
    for m in nearby_singles(magnitude, 16):
        if m == 0.0:
            continue
        direction = Vec3(f32(force.x / m), f32(force.y / m), f32(force.z / m))
        unit = normalized(direction)
        if (f32(m * unit.x), f32(m * unit.y), f32(m * unit.z)) == (force.x, force.y, force.z):
            return direction, m
    return None


def _emit_terrain_repel(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags0: int, path: str) -> None:
    if not bit(flags0, 10):
        coverage.emitted()
        return
    line = f"terrainRepel {fmt_vec2_pair(p.terrain_repel)}"
    if p.scout.value != 0.0:
        line += f" -scout {fmt_num(p.scout.value)}"
    if p.vertical.value != 0.0:
        line += f" -vertical {fmt_num(p.vertical.value)}"
    if p.kill_height.value != PARTICLE_DEFAULT.kill_height.value:
        line += f" -killHeight {fmt_num(p.kill_height.value)}"
    writer.line(line)
    coverage.emitted()


def _emit_warp(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags2: int, path: str) -> None:
    has_uv = p.uv_scale.value != PARTICLE_DEFAULT.uv_scale.value or p.uv_range != PARTICLE_DEFAULT.uv_range
    has_alpha = (
        p.alpha_warp_direction != PARTICLE_DEFAULT.alpha_warp_direction
        or p.alpha_warp_curve.items != PARTICLE_DEFAULT.alpha_warp_curve.items
    )

    # One -wiggle per warp command (the parser does not loop), and
    # `-wiggleDir amount a [b]` stores a at the record's second vector and
    # b at the first (cParticleWarpCommand, Mac 0x007880EC).
    for w in p.wiggles.items:
        line = f"warp -wiggleDir {fmt_num(w.amount.value)} {fmt_vec3_sample(w.uv)}"
        if _nz3(w.direction):
            line += f" {fmt_vec3_sample(w.direction)}"
        writer.line(line)

    parts = []
    if has_uv:
        parts.append(f"-uv {fmt_num(p.uv_scale.value)} {fmt_vec2_sample(p.uv_range)}")
    if has_alpha:
        curve = fmt_float_curve(p.alpha_warp_curve.items)
        # The parser normalizes the direction before storing it.
        direction = fit_unit(p.alpha_warp_direction) or p.alpha_warp_direction
        parts.append(f"-alpha {fmt_vec3_sample(direction)} {curve}".rstrip())
    if bit(flags2, 8) and not has_uv and not has_alpha:
        parts.append("-wiggleVerts")
    if parts:
        writer.line(" ".join(["warp", *parts]))
    coverage.emitted()


def _emit_random_walk(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags0: int, path: str) -> None:
    if not bit(flags0, 23):
        coverage.emitted()
        return
    writer.begin_command("randomWalk")
    # -delay and -strength are base-plus-variation, -turn stores its two
    # arguments directly (cParticleRandomWalkCommand, Mac 0x0077FC62).
    if p.random_walk_delay != PARTICLE_DEFAULT.random_walk_delay:
        writer.line(_base_vary_switch(coverage, "-delay", p.random_walk_delay, f"{path}.random_walk_delay"))
    if p.random_walk_strength != PARTICLE_DEFAULT.random_walk_strength:
        writer.line(_base_vary_switch(coverage, "-strength", p.random_walk_strength, f"{path}.random_walk_strength"))
    if p.random_walk_turn != PARTICLE_DEFAULT.random_walk_turn:
        writer.line(f"-turn {fmt_vec2_pair(p.random_walk_turn)}")
    if bit(flags0, 24):
        writer.line("-wait")
    if bit(flags0, 25):
        writer.line("-preferSea")
    if p.prefer_direction != PARTICLE_DEFAULT.prefer_direction:
        # One quoted argument: randomWalk's parser runs ParseVector3 over a
        # single switch argument (Mac `0x0077fc62`).
        writer.line(f"-preferDir {fmt_vec3_sample(p.prefer_direction)}")
    writer.end_command()
    coverage.emitted()


def _base_vary_switch(coverage: Coverage, switch: str, value: Vec2, path: str) -> str:
    base, vary, exact = fit_base_vary(value.x, value.y)
    if not exact:
        coverage.note(path, "unsupported", f"stored range has no exact {switch} base-plus-variation spelling, the nearest was emitted")
    return f"{switch} {fmt_num(base)}" + (f" {fmt_num(vary)}" if vary != 0.0 else "")


def _emit_collision(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags0: int, flags1: int, path: str) -> None:
    if not bit(flags0, 8):
        coverage.emitted()
        return
    # Registered as `collide` (particle command table, Mac 0x00782EB6),
    # so a `collision` line is rejected with `Unknown command`.
    writer.begin_command("collide")
    if p.bounce.value != 0.3:
        writer.line(f"-bounce {fmt_num(p.bounce.value)}")
    if bit(flags0, 9):
        writer.line("-sticky")
    # Bit 11 is already emitted canonically on `source`; the collision
    # spelling writes the identical stored bit.
    if p.collision_effect_or_death.value != 0.0:
        # `-effect` and `-death` share one field with no distinguishing bit
        # (effdir.md, "collision_effect_or_death"); `-death` additionally
        # clamps through [0,1] on the way in, which is not reversible.
        writer.line(f"-effect {fmt_num(p.collision_effect_or_death.value)}")
    if p.death_by_water.value != PARTICLE_DEFAULT.death_by_water.value:
        writer.line(f"-deathByWater {fmt_num(p.death_by_water.value)}")
    if bit(flags1, 0):
        writer.line("-destroyBuildings")
    writer.end_command()
    coverage.emitted()


def _emit_appearance(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, path: str) -> None:
    if p.color_curve.items != PARTICLE_DEFAULT.color_curve.items or p.color_vary != PARTICLE_DEFAULT.color_vary:
        line = "color"
        if p.color_curve.items:
            line += " " + fmt_color_curve(p.color_curve.items)
        if p.color_vary != PARTICLE_DEFAULT.color_vary:
            line += f" -vary {fmt_vec3_sample(p.color_vary)}"
        writer.line(line)
    coverage.emitted()

    if p.alpha_curve.items != PARTICLE_DEFAULT.alpha_curve.items or p.alpha_vary.value != PARTICLE_DEFAULT.alpha_vary.value:
        line = "alpha"
        if p.alpha_curve.items:
            line += " " + fmt_float_curve(p.alpha_curve.items)
        if p.alpha_vary.value != PARTICLE_DEFAULT.alpha_vary.value:
            line += f" -vary {fmt_num(p.alpha_vary.value)}"
        writer.line(line)
    coverage.emitted()

    if p.size_curve.items != PARTICLE_DEFAULT.size_curve.items or p.size_vary.value != PARTICLE_DEFAULT.size_vary.value:
        line = "size"
        if p.size_curve.items:
            # particle.size.curve: "parser multiplies size-curve inputs by
            # 50 before storing" (catalog.py) -- inverted here.
            line += " " + " ".join(fmt_scaled(v, 50.0) for v in p.size_curve.items)
        if p.size_vary.value != PARTICLE_DEFAULT.size_vary.value:
            line += f" -vary {fmt_num(p.size_vary.value)}"
        writer.line(line)
    coverage.emitted()

    if p.aspect_curve.items != PARTICLE_DEFAULT.aspect_curve.items or p.aspect_vary.value != PARTICLE_DEFAULT.aspect_vary.value:
        line = "aspect"
        if p.aspect_curve.items:
            line += " " + fmt_float_curve(p.aspect_curve.items)
        if p.aspect_vary.value != PARTICLE_DEFAULT.aspect_vary.value:
            line += f" -vary {fmt_num(p.aspect_vary.value)}"
        writer.line(line)
    coverage.emitted()

    if (
        p.rotate_curve.items != PARTICLE_DEFAULT.rotate_curve.items
        or p.rotate_vary.value != PARTICLE_DEFAULT.rotate_vary.value
        or p.rotate_offset.value != PARTICLE_DEFAULT.rotate_offset.value
    ):
        line = "rotate"
        if p.rotate_curve.items:
            line += " " + fmt_float_curve(p.rotate_curve.items)
        if p.rotate_vary.value != PARTICLE_DEFAULT.rotate_vary.value:
            line += f" -vary {fmt_num(p.rotate_vary.value)}"
        if p.rotate_offset.value != PARTICLE_DEFAULT.rotate_offset.value:
            line += f" -offset {fmt_num(p.rotate_offset.value)}"
        writer.line(line)
    coverage.emitted()

    if p.stretch.value != 0.0:
        writer.line(f"stretch {fmt_num(p.stretch.value)}")
    coverage.emitted()


def _emit_texture_model_align(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags0: int, flags2: int, path: str) -> None:
    is_model = bit(flags2, 0)
    shared_draw = []
    if bit(flags0, 0):
        shared_draw.append("-light")
    if bit(flags0, 4):
        shared_draw.append("-noCull")
    if p.sort_offset.value != 0.0:
        shared_draw.append(f"-sortOffset {fmt_num(p.sort_offset.value)}")
    expected_draw = 3 if is_model else 0
    if p.draw_mode.value != expected_draw:
        draw_name = _PARTICLE_DRAW_TYPES.get(p.draw_mode.value)
        if draw_name is None:
            coverage.note(
                f"{path}.draw_mode",
                "unsupported",
                f"draw_mode={int(p.draw_mode.value)} is outside the confirmed enum range 0..7",
            )
        else:
            shared_draw.insert(0, f"-draw {draw_name}")

    if is_model:
        names = [fmt_asset_name("modelID", k) for k in p.model_keys.items] or [fmt_asset_name("modelID", p.resource_key.value)]
        writer.begin_command("model " + " ".join(names))
        for opt in shared_draw:
            writer.line(opt)
        if bit(flags2, 1):
            writer.line("-fakePerspective")
        if bit(flags2, 3):
            writer.line("-moveEntireSlave")
        if bit(flags2, 4):
            writer.line("-applyAlpha")
        if bit(flags2, 6):
            writer.line(f"-modelSpeed {fmt_num(p.model_speed_static.value)}")
        elif p.model_speed_static.value != PARTICLE_DEFAULT.model_speed_static.value:
            writer.line(f"-modelSpeedStatic {fmt_num(p.model_speed_static.value)}")
        if bit(flags2, 5):
            writer.line("-sustain")
        if bit(flags2, 2):
            writer.line("-applyLighting")
        if bit(flags2, 10):
            writer.line("-noCullFaces")
        writer.end_command()
        coverage.emitted()
    elif p.resource_key.value != 0:
        line = f"texture {fmt_asset_name('textureID', p.resource_key.value)}"
        if bit(flags0, 29):
            line += " -hflip"
        if bit(flags0, 30):
            line += " -vflip"
        line += "".join(f" {opt}" for opt in shared_draw)
        writer.line(line)
        coverage.emitted()
    else:
        if shared_draw:
            coverage.note(
                f"{path}.draw_mode",
                "unsupported",
                "draw/light/cull/sort options are stored, but no texture or model command exists to carry them",
            )
        coverage.emitted()

    align_active = (
        p.alignment_mode.value != PARTICLE_DEFAULT.alignment_mode.value
        or p.alignment_damp.value != PARTICLE_DEFAULT.alignment_damp.value
        or p.bank_range != PARTICLE_DEFAULT.bank_range
        or bit(flags2, 7)
    )
    if align_active:
        align_name = _ALIGN_TYPES.get(p.alignment_mode.value)
        if align_name is None:
            coverage.note(
                f"{path}.alignment_mode",
                "unsupported",
                f"alignment_mode={int(p.alignment_mode.value)} is outside the confirmed enum range 0..4",
            )
        else:
            line = f"align {align_name}"
            if p.alignment_damp.value != PARTICLE_DEFAULT.alignment_damp.value:
                line += f" -damp {fmt_num(p.alignment_damp.value)}"
            if p.bank_range != PARTICLE_DEFAULT.bank_range or bit(flags2, 7):
                bank_switch = "-windBank" if bit(flags2, 7) else "-bank"
                line += f" {bank_switch} {fmt_vec2_pair(p.bank_range)}"
            writer.line(line)
    coverage.emitted()


def _emit_timed_effects(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, path: str) -> None:
    effect_base = p.terrain_name.decoded or ""
    if effect_base:
        # `effectBase` writes this string (cParticleEffectBaseCommand, Mac
        # 0x0078A6DA), the record's only source of the field.
        writer.line(f"effectBase {quote_name(effect_base)}")
    for te in p.timed_effects.items:
        name = te.effect_name.decoded or ""
        if name:
            writer.line(f"timedEffect {quote_name(name)} {fmt_num(te.time.value)}")
    coverage.emitted()


def particle_asset_ids(p: ParticleDescriptor) -> List[Tuple[str, int]]:
    """The `modelID`/`textureID` bindings `emit_particles` references by name.

    Mirrors the model-vs-texture dispatch in `_emit_texture_model_align`:
    third-bitset bit 0 selects `model` (one key per name, from the vector or
    the single key), anything else with a key emits `texture`.
    """

    if bit(p.flags_2.value, 0):
        keys = list(p.model_keys.items) or [p.resource_key.value]
        return [("modelID", int(k)) for k in keys]
    if p.resource_key.value != 0:
        return [("textureID", int(p.resource_key.value))]
    return []
