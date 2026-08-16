"""EFFDIR `DynamicParticleDescriptor` -> fx `dynamicParticle NAME ... end`.

Mapping from `docs/reference/top-level/dynamic-particle.md`."""

from __future__ import annotations

from ..model.dynamic_particle import DynamicParticleDescriptor
from .coverage import Coverage
from .defaults import DYNAMIC_PARTICLE_DEFAULT
from .writer import FxWriter, fmt_hex, fmt_num, quote_name


def emit_dynamic_particle(writer: FxWriter, coverage: Coverage, name: str, d: DynamicParticleDescriptor, *, path: str) -> None:
    writer.begin(f"dynamicParticle {quote_name(name)}")

    base_name = d.base_name.decoded or ""
    if base_name:
        writer.line(f"effectBase {quote_name(base_name)}")
    coverage.emitted()

    if d.model_keys.items or d.model_key.value != 0:
        names = [fmt_hex(k) for k in d.model_keys.items] or [fmt_hex(d.model_key.value)]
        writer.line("model " + " ".join(names))
    coverage.emitted()

    if d.mass.value != DYNAMIC_PARTICLE_DEFAULT.mass.value:
        writer.line(f"mass {fmt_num(d.mass.value)}")
    coverage.emitted()

    if d.friction_min.value != 0.0 or d.friction_max.value != 0.0 or d.angular_friction.value != 0.0:
        writer.line(f"friction {fmt_num(d.friction_min.value)} {fmt_num(d.friction_max.value)} -angular {fmt_num(d.angular_friction.value)}")
    coverage.emitted()

    if d.flags.value != 0:
        coverage.note(f"{path}.flags", "unsupported", f"flags={int(d.flags.value)} has no confirmed parser setter or runtime consumer")
    if d.value_14.value != 0.0 or d.value_24.value != 0.0:
        coverage.note(f"{path}", "unsupported", f"value_14={d.value_14.value!r}/value_24={d.value_24.value!r} have no confirmed parser setter or runtime consumer")

    writer.end()
