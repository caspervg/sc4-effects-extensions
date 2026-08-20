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
from typing import List, Tuple

from ..model.particle import ParticleDescriptor
from ..wire import Bounds3, Vec2, Vec3
from .bits import bit
from .coverage import Coverage
from .defaults import PARTICLE_DEFAULT
from .writer import FxWriter, fmt_asset_name, fmt_color_curve, fmt_float_curve, fmt_hex, fmt_num, fmt_vec2_pair, fmt_vec2_sample, fmt_vec3_sample, quote_name


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

    # `terrain_name` is compiler lineage/name metadata. The flattened
    # descriptor above preserves behavior, and no runtime consumer is known.
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
        line = f"life {fmt_vec2_pair(p.life)}"
        if p.preroll.value != 0.0:
            line += f" -preroll {fmt_num(p.preroll.value)}"
        writer.line(line)
        coverage.emitted()
    else:
        coverage.emitted()  # nothing to emit and nothing lost -- both zero


def _emit_emission(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags0: int, path: str) -> None:
    has_curve = p.emit_curve.items != PARTICLE_DEFAULT.emit_curve.items
    is_maintain = bit(flags0, 2)
    is_inject = bit(flags0, 1)
    shared = _emission_shared_options(p, flags0)
    has_motion = (
        p.emit_velocity_bounds != PARTICLE_DEFAULT.emit_velocity_bounds
        or p.emit_speed != PARTICLE_DEFAULT.emit_speed
        or bit(flags0, 5)
    )
    if not (has_curve or is_maintain or is_inject or shared or has_motion):
        coverage.emitted()
        return

    if is_maintain:
        value = p.emit_curve.items[0] if p.emit_curve.items else 0.0
        if is_inject:
            writer.line(f"emit -inject {fmt_num(value)}")
        writer.line(f"maintain {fmt_num(value)}{shared}")
        if len(p.emit_curve.items) > 1:
            coverage.note(
                f"{path}.emit_curve",
                "info",
                f"maintain takes a single value but {len(p.emit_curve.items)} curve samples are stored; "
                "only the first was emitted",
            )
        coverage.emitted()
    elif has_curve or is_inject:
        if is_inject:
            value = p.emit_curve.items[0] if p.emit_curve.items else 0.0
            writer.line(f"emit -inject {fmt_num(value)}{shared}")
            if len(p.emit_curve.items) > 1:
                coverage.note(
                    f"{path}.emit_curve",
                    "unsupported",
                    f"inject mode stores one value but {len(p.emit_curve.items)} curve samples are present; only the first can be emitted",
                )
        else:
            writer.line(f"emit -rate {fmt_float_curve(p.emit_curve.items)}{shared}")
        coverage.emitted()
    elif shared:
        writer.line("emit" + shared)
        coverage.emitted()

    # Initial-motion options live on `emit` regardless of whether the rate
    # itself was spelled `emit`/`inject`/`rate` or `maintain`; emitting
    # them unconditionally keeps a maintain-mode particle's velocity and
    # speed from being dropped (they are stored in the same descriptor).
    motion = []
    if p.emit_velocity_bounds != PARTICLE_DEFAULT.emit_velocity_bounds:
        # `-velocity` takes ONE argument -- a single quoted direction that
        # `nSCRes::ParseVector3` reads out of that one string (emit parser,
        # Mac `0x00786ac1`), which the parser stores as both ends of the
        # bounds. Two bare vec3s were six separate tokens the parser would
        # read as a malformed direction plus stray speed/vary arguments.
        motion.append(f"-velocity {fmt_vec3_sample(p.emit_velocity_bounds.minimum)}")
        if p.emit_velocity_bounds.minimum != p.emit_velocity_bounds.maximum:
            coverage.note(
                f"{path}.emit_velocity_bounds",
                "unsupported",
                "stored velocity bounds have different minimum and maximum, but `-velocity` writes one "
                "direction to both ends; only the minimum was emitted",
            )
    if p.emit_speed != PARTICLE_DEFAULT.emit_speed:
        motion.append(f"-speed {fmt_num(p.emit_speed.x)} {fmt_num(p.emit_speed.y)}")
    if bit(flags0, 5):
        motion.append("-base")
    if motion:
        writer.line("emit " + " ".join(motion))
        coverage.emitted()
    else:
        coverage.emitted()


def _emission_shared_options(p: ParticleDescriptor, flags0: int) -> str:
    parts = []
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
    return (" " + " ".join(parts)) if parts else ""


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

    if has_dice:
        writer.line(f"source -dice {fmt_num(p.model_speed.value)}")
        if bounds == _ZERO_BOUNDS and not has_filters:
            coverage.emitted()
            return

    options = []
    if bit(flags0, 6):
        options.append("-model")
    if bit(flags0, 7):
        options.append("-modelBase")
    if bit(flags0, 13):
        options.append("-cityWindySide")
    elif bit(flags0, 12):
        options.append("-city")
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
    if bit(flags0, 22):
        options.append("-scaleParticles")
    if bit(flags2, 9):
        options.append("-resetIncoming")
    if bit(flags0, 11):
        options.append("-killOutsideCity")

    # A source command with no shape creates a flat [-1,0,-1]..[1,0,1]
    # box. Emit canonical -box half-extents plus optional center whenever
    # that implicit box would not reproduce the stored bounds.
    if bounds != _SOURCE_COMMAND_DEFAULT_BOUNDS:
        half = Vec3(
            (bounds.maximum.x - bounds.minimum.x) / 2.0,
            (bounds.maximum.y - bounds.minimum.y) / 2.0,
            (bounds.maximum.z - bounds.minimum.z) / 2.0,
        )
        center = Vec3(
            (bounds.maximum.x + bounds.minimum.x) / 2.0,
            (bounds.maximum.y + bounds.minimum.y) / 2.0,
            (bounds.maximum.z + bounds.minimum.z) / 2.0,
        )
        shape = f"-box {fmt_vec3_sample(half)}"
        if _nz3(center):
            shape += f" {fmt_vec3_sample(center)}"
        options.insert(0, shape)

    if options:
        writer.line("source " + " ".join(options))
        coverage.emitted()
    else:
        # Reproduces cParticleSourceCommand's own flat default box.
        writer.line("source")
        coverage.emitted()


def _emit_force(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags0: int, path: str) -> None:
    parts = []
    if _nz3(p.force):
        magnitude = math.sqrt(p.force.x * p.force.x + p.force.y * p.force.y + p.force.z * p.force.z)
        direction = Vec3(p.force.x / magnitude, p.force.y / magnitude, p.force.z / magnitude)
        parts.append(f"-wind {fmt_vec3_sample(direction)} {fmt_num(magnitude)}")
    if p.global_wind.value != 0.0:
        parts.append(f"-global_wind {fmt_num(p.global_wind.value)}")
    if p.drag.value != 0.0:
        parts.append(f"-drag {fmt_num(p.drag.value)}")
    if p.screw.value != 0.0:
        # warp's `-screw` writes the same field scaled by 0.02 (warp.md);
        # the raw stored value is emitted as force's own -screw, which is
        # the simpler of the two equally-valid readings.
        parts.append(f"-screw {fmt_num(p.screw.value)}")
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
            parts.append(f"-automata {int(p.automata_id.value)} {fmt_num(p.attractor_strength.value)}")
        else:
            parts.append(f"-attractor {fmt_num(p.attractor_strength.value)} {curve}".rstrip())

    if len(p.tractor_points.items) > 0 or bit(flags0, 28):
        previous_end = 0.0
        for index, tp in enumerate(p.tractor_points.items):
            # Always written as an absolute point with an explicit tangent
            # vector: -tractorRel's chaining is resolved into the same
            # absolute-position storage before it reaches the wire, and
            # the wire never distinguishes an auto-derived tangent from an
            # explicitly authored one (force.md, "Second argument forms").
            line = f"-tractor {fmt_vec3_sample(tp.position)} {fmt_vec3_sample(tp.direction)}"
            duration = tp.amount.value - tp.time.value
            if duration != 0.0:
                line += f" {fmt_num(duration)}"
            parts.append(line)
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
        coverage.emitted()
    else:
        coverage.emitted()


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
    has_wiggle = len(p.wiggles.items) > 0

    if not (has_uv or has_alpha or has_wiggle or bit(flags2, 8)):
        coverage.emitted()
        return

    parts = []
    for w in p.wiggles.items:
        line = f"-wiggleDir {fmt_num(w.amount.value)} {fmt_vec3_sample(w.direction)}"
        if _nz3(w.uv):
            line += f" {fmt_vec3_sample(w.uv)}"
        parts.append(line)
    if has_uv:
        parts.append(f"-uv {fmt_num(p.uv_scale.value)} {fmt_vec2_sample(p.uv_range)}")
    if has_alpha:
        curve = fmt_float_curve(p.alpha_warp_curve.items)
        parts.append(f"-alpha {fmt_vec3_sample(p.alpha_warp_direction)} {curve}".rstrip())
    if bit(flags2, 8) and not has_uv and not has_alpha and not has_wiggle:
        parts.append("-wiggleVerts")

    if parts:
        writer.begin_command("warp")
        for part in parts:
            writer.line(part)
        writer.end_command()
        coverage.emitted()
    else:
        coverage.emitted()


def _emit_random_walk(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags0: int, path: str) -> None:
    if not bit(flags0, 23):
        coverage.emitted()
        return
    writer.begin_command("randomWalk")
    if p.random_walk_delay != PARTICLE_DEFAULT.random_walk_delay:
        writer.line(f"-delay {fmt_vec2_pair(p.random_walk_delay)}")
    if p.random_walk_strength != PARTICLE_DEFAULT.random_walk_strength:
        writer.line(f"-strength {fmt_vec2_pair(p.random_walk_strength)}")
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


def _emit_collision(writer: FxWriter, coverage: Coverage, p: ParticleDescriptor, flags0: int, flags1: int, path: str) -> None:
    if not bit(flags0, 8):
        coverage.emitted()
        return
    writer.begin_command("collision")
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
            scaled = [v / 50.0 for v in p.size_curve.items]
            line += " " + fmt_float_curve(scaled)
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
