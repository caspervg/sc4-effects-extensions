"""Top-level orchestration: `EffDirResource` -> a whole `.fx` source file,
or just the slice needed to reproduce one effect.

Emission order follows the language's own dependency direction (docs/
syntax/overview.md, "Practical model"): named pools first (`particles`,
`decal`, `shake`, `light`, `dynamicParticle`, `sequenceEffect`), then `effect`
blocks that reference them, then the two effect-name bindings
(`effectID`/`effectGroup`, `messageTrigger`) that reference effects by
name and so must come after they exist. Within the `effect` blocks
themselves, effect-to-effect references (`visualEffect` and friends -- see
`_effect_reference_order`) impose their own dependency order: a
`visualEffect` target must already exist when the referencing effect is
parsed, so effects are topologically sorted rather than emitted in raw
record order.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..model.resource import EffDirResource
from .coverage import Coverage, FxEmitResult, note_non_finite_floats
from .decals import decal_asset_ids, emit_decal
from .dynamic_particles import dynamic_particle_asset_ids, emit_dynamic_particle
from .effects import emit_effect, emit_effect_alias
from .inline_components import automata_effect_lines, brush_effect_lines, camera_effect_lines, scrubber_effect_lines, sound_effect_lines
from .lights import emit_light
from .names import ResolvedNames, resolve_names
from .particles import emit_particles, particle_asset_ids
from .sequences import emit_sequence
from .shakes import emit_shake
from .defaults import EFFECT_DEFAULT
from .profiles import GAME, CompilerProfile
from .writer import FxWriter, fmt_asset_name, fmt_hex, fmt_num, quote_name

_HEADER = (
    "This file was decompiled from an EFFDIR resource. It is a lossy, "
    "one-way reconstruction. See the coverage report for what could not "
    "be represented."
)


def _emit_inline_resource_ids(
    writer: FxWriter,
    coverage: Coverage,
    resource: EffDirResource,
    names: ResolvedNames,
    effect_indices: List[int],
    extra: Tuple[Tuple[int, int], ...] = (),
) -> None:
    """Declare the numeric lookup tables required by brush/sound children."""

    emitted = set()

    def declare(component_type: int, index: int) -> None:
        if component_type == 3 and 0 <= index < len(resource.components.brushes.items):
            key = resource.components.brushes.items[index].key.value
            keyword = "brushID"
        elif component_type == 7 and 0 <= index < len(resource.components.sounds.items):
            key = resource.components.sounds.items[index].resource_key.value
            keyword = "soundID"
        else:
            return
        identity = (keyword, key)
        if identity in emitted:
            return
        emitted.add(identity)
        writer.line(f"{keyword} {quote_name(names.name_for(component_type, index))} {fmt_hex(key)}")
        coverage.emitted()

    for effect_index in effect_indices:
        for description in resource.effect_descriptions.items[effect_index].descriptions.items:
            declare(description.component_type.value, description.description_index.value)
    for component_type, index in extra:
        declare(component_type, index)
    if emitted:
        writer.blank()


_ASSET_ID_SOURCES = {
    "particles": ("particles", particle_asset_ids),
    "decals": ("decals", decal_asset_ids),
    "dynamic_particles": ("dynamic_particles", dynamic_particle_asset_ids),
}


def _emit_asset_ids(writer: FxWriter, resource: EffDirResource, pools: Set[Tuple[str, int]]) -> None:
    """Declare the `textureID`/`modelID` names the emitted pools reference.

    Same job as `_emit_inline_resource_ids` does for brush/sound: EFFDIR
    stores a raw resource key, but `texture`/`model` only accept a symbolic
    name resolved through those maps, so a decompiled file that printed the
    key inline fails to load with `No such texture: '0x...'`. The alias is
    derived from the key itself (`fmt_asset_name`), so equal keys share one
    declaration and the output is stable across exports.

    No coverage accounting here: the texture/model fields these bindings
    exist for are already counted by their own emitters.
    """

    keys = []
    for collection_path, index in sorted(pools):
        source = _ASSET_ID_SOURCES.get(collection_path)
        if source is None:
            continue
        attribute, asset_ids = source
        items = getattr(resource, attribute).items
        if not 0 <= index < len(items):
            continue
        for binding in asset_ids(items[index]):
            if binding not in keys:
                keys.append(binding)

    for keyword, key in keys:
        writer.line(f"{keyword} {fmt_asset_name(keyword, key)} {fmt_hex(key)}")
    if keys:
        writer.blank()


def _emit_camera_params(writer: FxWriter, coverage: Coverage, resource: EffDirResource) -> None:
    """Emit the optional resource-wide cSC4CameraParams value."""

    metadata = resource.trailing_float_metadata
    if metadata.present.value == 0:
        return
    path = "trailing_float_metadata"
    if metadata.marker is None or metadata.count is None or metadata.values is None:
        coverage.skipped(path, "cameraParams is marked present but its wire value is incomplete")
        return

    count = metadata.count.value
    values = metadata.values
    if len(values) != count + 4:
        coverage.skipped(path, f"cameraParams has {len(values)} floats but its zoom count requires {count + 4}")
        return

    note_non_finite_floats(metadata, path, coverage)
    if metadata.marker.value != 0:
        coverage.skipped(f"{path}.marker", "cameraParams source always serializes marker 0")

    zooms = list(values[:count])
    parallax_base, parallax_range, size, side_swipe = values[count:]

    # `camera` takes any number of positional zoom values, and a single one is
    # expanded to five by repeated halving (cCameraParamsCommand, Mac
    # 0x0078600E), so use that shorter form only when it reproduces them.
    if len(zooms) == 5 and all(zooms[i] == zooms[0] * (0.5 ** i) for i in range(5)):
        source_zooms = zooms[:1]
    else:
        source_zooms = zooms

    # The command token is `camera`, not the class name: RegisterCommands
    # (Mac `0x00402931`) registers cCameraParamsCommand under "camera".
    parts = ["camera", *(fmt_num(value) for value in source_zooms)]
    if parallax_base != 100.0 or parallax_range != 1.0:
        if parallax_range < 0.0:
            coverage.skipped(f"{path}.parallax_range", "cameraParams clamps a negative parallax range to zero")
        parts.extend(("-parallax", fmt_num(parallax_base), fmt_num(parallax_base + max(parallax_range, 0.0))))
    if size != 4.0:
        parts.extend(("-size", fmt_num(size)))
    if side_swipe != 7.0:
        parts.extend(("-sideSwipe", fmt_num(side_swipe)))
    writer.line(" ".join(parts))
    coverage.emitted(5)
    writer.blank()


def _emit_pools(writer: FxWriter, coverage: Coverage, resource: EffDirResource, names: ResolvedNames, profile: CompilerProfile) -> None:
    for index, particle in enumerate(resource.particles.items):
        name = names.by_collection.get(("particles", index), f"particle_{index}")
        note_non_finite_floats(particle, f"particles[{index}]", coverage)
        emit_particles(writer, coverage, name, particle, path=f"particles[{index}]", profile=profile)
        writer.blank()

    for index, decal in enumerate(resource.decals.items):
        name = names.by_collection.get(("decals", index), f"decal_{index}")
        note_non_finite_floats(decal, f"decals[{index}]", coverage)
        emit_decal(writer, coverage, name, decal, path=f"decals[{index}]")
        writer.blank()

    for index, shake in enumerate(resource.shakes.items):
        name = names.shakes.get(index, f"shake_{index}")
        note_non_finite_floats(shake, f"shakes[{index}]", coverage)
        emit_shake(writer, coverage, name, shake, path=f"shakes[{index}]")
        writer.blank()

    for index, light in enumerate(resource.lights.items):
        name = names.lights.get(index, f"light_{index}")
        note_non_finite_floats(light, f"lights[{index}]", coverage)
        emit_light(writer, coverage, name, light, path=f"lights[{index}]")
        writer.blank()

    for index, dp in enumerate(resource.dynamic_particles.items):
        name = names.by_collection.get(("dynamic_particles", index), f"dynamic_particle_{index}")
        note_non_finite_floats(dp, f"dynamic_particles[{index}]", coverage)
        emit_dynamic_particle(writer, coverage, name, dp, path=f"dynamic_particles[{index}]")
        writer.blank()

    for index, sequence in enumerate(resource.components.sequences.items):
        name = names.by_collection.get(("components.sequences", index), f"sequence_{index}")
        emit_sequence(writer, coverage, name, sequence, path=f"components.sequences[{index}]")
        writer.blank()


def _emit_effects(writer: FxWriter, coverage: Coverage, resource: EffDirResource, names: ResolvedNames, profile: CompilerProfile) -> None:
    # visualEffect requires its target to already be defined
    # (docs/reference/effect-children/visual-effect.md), so raw record
    # order is not safe to emit directly -- an effect referencing a later
    # one via visualEffect would come before its own dependency exists.
    plan = _effect_emission_plan(resource, coverage)
    deferred_after: Dict[int, List[int]] = {}
    for real, predecessor in plan.deferred.items():
        if real != predecessor:
            deferred_after.setdefault(predecessor, []).append(real)

    def primary_name(effect_index: int) -> str:
        aliases = [a for a in names.effect_names.get(effect_index, []) if a]
        return aliases[0] if aliases else f"effect_{effect_index}"

    def ghost(effect_index: int, orphans: List[Tuple[int, int]], children: int = 0) -> None:
        _emit_ghost(writer, coverage, resource, names, effect_index, primary_name(effect_index), orphans, children)

    def child_count(effect_index: int) -> int:
        return len(resource.effect_descriptions.items[effect_index].descriptions.items)

    def emit_real(effect_index: int) -> None:
        for _ in range(plan.redefinitions.get(effect_index, 0) - 1):
            ghost(effect_index, [], child_count(effect_index))
        if effect_index in plan.orphans and effect_index not in plan.redefinitions:
            ghost(effect_index, plan.orphans[effect_index])
        effect = resource.effect_descriptions.items[effect_index]
        aliases = [a for a in names.effect_names.get(effect_index, []) if a] or [f"effect_{effect_index}"]
        primary, *extra = aliases
        note_non_finite_floats(effect, f"effect_descriptions[{effect_index}]", coverage)
        emit_effect(writer, coverage, resource, names, effect_index, effect, primary, profile)
        writer.blank()
        for alias in extra:
            emit_effect_alias(writer, primary, alias)
            coverage.note(
                f"effect_descriptions[{effect_index}]",
                "info",
                f"effect has multiple names ({', '.join(aliases)}); {alias!r} was emitted as a wrapper "
                f"effect calling visualEffect {primary!r} rather than a duplicate full definition",
            )
            writer.blank()

    def flush(after: int) -> None:
        for real in deferred_after.pop(after, []):
            emit_real(real)
            flush(real)

    for effect_index in range(len(resource.effect_descriptions.items)):
        if effect_index in plan.deferred:
            if effect_index in plan.redefinitions:
                ghost(effect_index, plan.orphans.get(effect_index, []), child_count(effect_index))
            else:
                ghost(effect_index, [])
            if plan.deferred[effect_index] != effect_index:
                continue
        emit_real(effect_index)
        flush(effect_index)


def _emit_bindings(writer: FxWriter, resource: EffDirResource) -> None:
    groups: "OrderedDict[int, list]" = OrderedDict()
    for entry in resource.effect_key_map.items:
        groups.setdefault(entry.group_id.value, []).append(entry)

    any_bindings = bool(groups) or bool(resource.message_triggers.items)
    if not any_bindings:
        return

    for group_id, entries in groups.items():
        if len(entries) == 1:
            e = entries[0]
            writer.line(f"effectID {fmt_hex(group_id)} {int(e.instance_id.value)} {quote_name(e.name.decoded or '')}")
        else:
            writer.begin(f"effectGroup {fmt_hex(group_id)}")
            for e in entries:
                writer.line(f"instance {int(e.instance_id.value)} {quote_name(e.name.decoded or '')}")
            writer.end()
    if groups:
        writer.blank()

    for trigger in resource.message_triggers.items:
        writer.line(f"messageTrigger {fmt_hex(trigger.message_id.value)} {quote_name(trigger.effect_name.decoded or '')}")


_ANON_POOLS = ((3, "brushes"), (4, "attractors"), (5, "scrubbers"), (7, "sounds"), (8, "cameras"))


@dataclass
class _EmissionPlan:
    """How record order maps to source order.

    Stored order is parser order, with three recoverable exceptions, all
    from an effect that was defined twice with the same name and priority:

    - `deferred` maps an effect to the effect its real definition must
      follow. Its index comes from an earlier definition (emitted as an
      empty *ghost* at its record position), while its anonymous children
      and its `visualEffect` targets were created later.
    - `orphans` maps an effect to anonymous pool records nothing references,
      each `(component_type, pool_index)`. The first definition of a
      redefined effect created them, then the second replaced it, so a
      ghost right before the real definition recreates them at the right
      pool position.
    - `redefinitions` maps an effect to how many times its children were
      assigned over, which is what the stored `revision` counts. An
      effect listed here is defined that many extra times with as many
      children, after the last growth of the effect vector, because growth
      zeroes the counters of every effect (see `_outer_growth_index`).
    """

    deferred: Dict[int, int] = field(default_factory=dict)
    orphans: Dict[int, List[Tuple[int, int]]] = field(default_factory=dict)
    redefinitions: Dict[int, int] = field(default_factory=dict)


def _outer_growth_index(count: int) -> int:
    """Index of the last effect whose addition reallocated the effect vector
    (capacity doubles from 1, so that is the largest power of two below
    `count`)."""

    index = 0 if count < 2 else 1
    while index and index * 2 < count:
        index *= 2
    return index


def _effect_emission_plan(resource: EffDirResource, coverage: Coverage) -> _EmissionPlan:
    plan = _EmissionPlan()
    effects = resource.effect_descriptions.items
    count = len(effects)
    by_name = _effect_indices_by_name(resource)
    owner: Dict[Tuple[int, int], int] = {}
    for effect_index, effect in enumerate(effects):
        for d in effect.descriptions.items:
            owner[(d.component_type.value, d.description_index.value)] = effect_index

    def pool_order(component_type: int) -> List[Tuple[int, int]]:
        pool = [(idx, ei) for (t, idx), ei in owner.items() if t == component_type]
        pool.sort()
        return pool

    predecessors: Dict[int, int] = {}
    for component_type, _attr in _ANON_POOLS:
        pool = pool_order(component_type)
        # Scanning in pool order, every effect must appear in record order, so
        # an effect placed earlier by record order than something with a
        # smaller pool index was really defined after that something.
        for position, (pool_index, effect_index) in enumerate(pool):
            later_smaller = [ei for _, ei in pool[:position] if ei > effect_index]
            if later_smaller:
                predecessors[effect_index] = max(predecessors.get(effect_index, 0), max(later_smaller))

    for effect_index, effect in enumerate(effects):
        for description in effect.descriptions.items:
            if description.component_type.value != 2:
                continue
            targets = by_name.get((description.name.decoded or "").casefold(), [])
            targets = [t for t in targets if 0 <= t < count]
            first = min(targets, default=None)
            if first is not None and first > effect_index:
                predecessors[effect_index] = max(predecessors.get(effect_index, 0), first)

    last_growth = _outer_growth_index(count)
    for effect_index, effect in enumerate(effects):
        revisions = {d.legacy_transform.revision.value & 0xFF for d in effect.descriptions.items}
        if not any(revisions):
            continue
        if len(revisions) != 1:
            coverage.note(
                f"effect_descriptions[{effect_index}]",
                "unsupported",
                f"children have unequal revision values {sorted(revisions)}, which equal-sized redefinitions cannot produce",
            )
        plan.redefinitions[effect_index] = max(revisions)
        predecessors[effect_index] = max(predecessors.get(effect_index, 0), max(last_growth, effect_index))

    plan.deferred = predecessors

    for component_type, attribute in _ANON_POOLS:
        total = len(getattr(resource.components, attribute).items)
        referenced = sorted(idx for (t, idx) in owner if t == component_type)
        for orphan in sorted(set(range(total)) - set(referenced)):
            nexts = [idx for idx in referenced if idx > orphan]
            if nexts:
                host = owner[(component_type, nexts[0])]
            else:
                # After the last user of this pool, so its own definition adds
                # nothing here and the ghost lands after every earlier record.
                last_user = max((owner[(component_type, idx)] for idx in referenced), default=-1)
                candidates = [i for i in range(last_user + 1, count) if not any(d.component_type.value == component_type for d in effects[i].descriptions.items)]
                host = candidates[-1] if candidates else None
            if host is None:
                coverage.note(f"components.{attribute}[{orphan}]", "unsupported", "unreferenced pool record with no effect to anchor a ghost definition, so it is dropped")
                continue
            plan.orphans.setdefault(host, []).append((component_type, orphan))
    for host, orphans in plan.orphans.items():
        if host >= last_growth and host not in plan.redefinitions and len(orphans) >= len(effects[host].descriptions.items):
            coverage.note(
                f"effect_descriptions[{host}]",
                "unsupported",
                "the ghost that recreates its orphaned pool records leaves a nonzero revision on this effect's children",
            )
    return plan


def _emit_ghost(
    writer: FxWriter,
    coverage: Coverage,
    resource: EffDirResource,
    names: ResolvedNames,
    effect_index: int,
    name: str,
    orphans: List[Tuple[int, int]],
    children: int = 0,
) -> None:
    """An effect body that a later definition of the same name and priority
    replaces: it fixes this name's record index (an empty ghost), recreates
    unreferenced anonymous pool records, or provides `children` slots for
    the next definition to assign over. Filler children name an existing
    pool so they leave nothing behind in any pool."""

    effect = resource.effect_descriptions.items[effect_index]
    header = f"effect {quote_name(name)}"
    if effect.priority.value != EFFECT_DEFAULT.priority.value:
        header += f" -priority {int(effect.priority.value)}"
    writer.begin(header)
    for component_type, index in sorted(orphans):
        lines = _anonymous_lines(resource, names, component_type, index, coverage)
        if lines:
            writer.multiline_command(lines)
    filler = _ghost_filler(resource, names, effect_index)
    missing = max(children - len(orphans), 0)
    if missing and filler is None:
        coverage.note(f"effect_descriptions[{effect_index}]", "unsupported", "no pool or earlier effect exists to fill the ghost's child slots, so its revision cannot be reproduced")
    elif missing:
        for _ in range(missing):
            writer.line(filler)
    writer.end()
    writer.blank()


def _ghost_filler(resource: EffDirResource, names: ResolvedNames, effect_index: int) -> Optional[str]:
    if resource.particles.items:
        return f"particleEffect {quote_name(names.by_collection.get(('particles', 0), 'particle_0'))}"
    if resource.decals.items:
        return f"decalEffect {quote_name(names.by_collection.get(('decals', 0), 'decal_0'))}"
    if resource.dynamic_particles.items:
        return f"dynamicParticleEffect {quote_name(names.by_collection.get(('dynamic_particles', 0), 'dynamic_particle_0'))}"
    if resource.components.sequences.items:
        return f"sequenceEffect {quote_name(names.by_collection.get(('components.sequences', 0), 'sequence_0'))}"
    earlier = next((n for i in range(effect_index) for n in names.effect_names.get(i, []) if n), None)
    return f"visualEffect {quote_name(earlier)}" if earlier else None


def _anonymous_lines(resource: EffDirResource, names: ResolvedNames, component_type: int, index: int, coverage: Coverage) -> List[str]:
    components = resource.components
    path = f"components[{component_type}][{index}]"
    if component_type == 3:
        return brush_effect_lines(names.name_for(3, index), components.brushes.items[index], coverage=coverage, path=path)
    if component_type == 4:
        record = components.attractors.items[index]
        return automata_effect_lines(record.name.decoded or "", record, coverage=coverage, path=path)
    if component_type == 5:
        return scrubber_effect_lines(components.scrubbers.items[index], coverage=coverage, path=path) or ["scrubberEffect", "-noFlora"]
    if component_type == 7:
        return sound_effect_lines(names.name_for(7, index), components.sounds.items[index], coverage=coverage, path=path)
    if component_type == 8:
        return camera_effect_lines(components.cameras.items[index], coverage=coverage, path=path) or ["cameraEffect"]
    return []


PREVIEWABLE_COLLECTIONS = frozenset(
    {
        "effect_descriptions",
        "particles",
        "decals",
        "shakes",
        "lights",
        "dynamic_particles",
        "components.sequences",
    }
)


def emit_descriptor(resource: EffDirResource, path: str) -> Optional[FxEmitResult]:
    """Decompile the single record at `path` on its own.

    For a live, per-selection preview (as opposed to a full resource or
    effect export). `effect_descriptions[i]` delegates to
    `emit_effect_closure` one level deep (not transitive), since an
    effect's own fx spelling depends on the pools its children reach. A
    pool record (particle/decal/shake/light/dynamic particle/sequence) is
    emitted alone, using the same name resolution a full export would use.
    Anything else -- a raw field, or a record from a collection with no
    standalone fx spelling (brush/attractor/scrubber/sound/camera only
    exist inline inside an effect body) -- returns None.
    """

    from ..editor import paths as _paths

    tokens = _paths.tokenize(path)
    if len(tokens) < 2 or not isinstance(tokens[-1], int):
        return None
    index = tokens[-1]
    collection = _paths.format_tokens(tokens[:-1])
    if collection not in PREVIEWABLE_COLLECTIONS:
        return None

    if collection == "effect_descriptions":
        return emit_effect_closure(resource, index, transitive=False)

    coverage = Coverage()
    writer = FxWriter()
    names = resolve_names(resource, coverage)
    _emit_asset_ids(writer, resource, {(collection, index)})

    if collection == "particles" and 0 <= index < len(resource.particles.items):
        item = resource.particles.items[index]
        name = names.by_collection.get(("particles", index), f"particle_{index}")
        note_non_finite_floats(item, path, coverage)
        emit_particles(writer, coverage, name, item, path=path)
    elif collection == "decals" and 0 <= index < len(resource.decals.items):
        item = resource.decals.items[index]
        name = names.by_collection.get(("decals", index), f"decal_{index}")
        note_non_finite_floats(item, path, coverage)
        emit_decal(writer, coverage, name, item, path=path)
    elif collection == "shakes" and 0 <= index < len(resource.shakes.items):
        item = resource.shakes.items[index]
        name = names.shakes.get(index, f"shake_{index}")
        note_non_finite_floats(item, path, coverage)
        emit_shake(writer, coverage, name, item, path=path)
    elif collection == "lights" and 0 <= index < len(resource.lights.items):
        item = resource.lights.items[index]
        name = names.lights.get(index, f"light_{index}")
        note_non_finite_floats(item, path, coverage)
        emit_light(writer, coverage, name, item, path=path)
    elif collection == "dynamic_particles" and 0 <= index < len(resource.dynamic_particles.items):
        item = resource.dynamic_particles.items[index]
        name = names.by_collection.get(("dynamic_particles", index), f"dynamic_particle_{index}")
        note_non_finite_floats(item, path, coverage)
        emit_dynamic_particle(writer, coverage, name, item, path=path)
    elif collection == "components.sequences" and 0 <= index < len(resource.components.sequences.items):
        item = resource.components.sequences.items[index]
        name = names.by_collection.get(("components.sequences", index), f"sequence_{index}")
        emit_sequence(writer, coverage, name, item, path=path)
    else:
        return None

    return FxEmitResult(text=writer.text(), coverage=coverage)


def emit_resource(resource: EffDirResource, profile: CompilerProfile = GAME) -> FxEmitResult:
    """Decompile an entire resource into one fx source document.

    `profile` selects the spellings for a non-game writer, matching the
    profile the text will be compiled with.
    """

    coverage = Coverage()
    writer = FxWriter()
    writer.comment(_HEADER)
    writer.blank()

    names = resolve_names(resource, coverage)
    effect_indices = list(range(len(resource.effect_descriptions.items)))
    orphan_ids = tuple(
        pair for pairs in _effect_emission_plan(resource, Coverage()).orphans.values() for pair in pairs
    )
    _emit_inline_resource_ids(writer, coverage, resource, names, effect_indices, orphan_ids)
    _emit_asset_ids(writer, resource, _all_pools(resource))
    _emit_camera_params(writer, coverage, resource)
    _emit_pools(writer, coverage, resource, names, profile)
    _emit_effects(writer, coverage, resource, names, profile)
    _emit_bindings(writer, resource)

    return FxEmitResult(text=writer.text(), coverage=coverage)


_INLINE_COLLECTIONS = (
    "components.brushes",
    "components.attractors",
    "components.scrubbers",
    "components.sounds",
    "components.cameras",
)


def _all_pools(resource: EffDirResource) -> Set[Tuple[str, int]]:
    """Every pool `_emit_pools` will emit, as (collection_path, index)."""

    return {
        (collection_path, index)
        for collection_path, (attribute, _) in _ASSET_ID_SOURCES.items()
        for index in range(len(getattr(resource, attribute).items))
    }


def _referenced_pools(resource: EffDirResource, effect_index: int) -> Set[Tuple[str, int]]:
    """(collection_path, index) pairs one effect's particle/decal/
    dynamicParticle/sequence children reach -- brush/attractor/scrubber/
    sound/camera are embedded inline in the effect body and need no
    separate pool export."""

    from ..editor.references import COMPONENT_COLLECTIONS

    effect = resource.effect_descriptions.items[effect_index]
    keys: Set[Tuple[str, int]] = set()
    for d in effect.descriptions.items:
        collection = COMPONENT_COLLECTIONS.get(d.component_type.value)
        if collection is None or collection[0] in _INLINE_COLLECTIONS:
            continue
        keys.add((collection[0], d.description_index.value))
    return keys


def _effect_indices_by_name(resource: EffDirResource) -> Dict[str, List[int]]:
    """Effect name -> description indices. The parser lowercases effect
    names before storing them (docs/reference/top-level/resource-binding.md),
    so lookups are case-folded to match how a name-based reference in one
    record resolves against `effect_name_map`."""

    table: Dict[str, List[int]] = {}
    for entry in resource.effect_name_map.items:
        name = (entry.name.decoded or "").casefold()
        if name:
            table.setdefault(name, []).append(entry.target.value)
    return table


def _effect_names_referenced_by(resource: EffDirResource, effect_index: int, pools: Set[Tuple[str, int]]) -> Set[str]:
    """Every *effect name* reachable from one effect and the pools it uses.

    Four documented name-based effect references exist:
      - `EffectDescription.chain_effect`  (chainEffect)
      - `ParticleDescriptor.timed_effects[].effect_name` (timedEffect)
      - `SequenceDescription.items[].effect_name` (sequence play items)
      - `DynamicParticleDescriptor.base_name` (effectBase)

    Component type 2 is a name-based `visualEffect` child and is followed
    through the effect-name map rather than through a component pool.
    """

    effect = resource.effect_descriptions.items[effect_index]
    found: Set[str] = set()

    chain = effect.chain_effect.decoded or ""
    if chain:
        found.add(chain)

    for description in effect.descriptions.items:
        if description.component_type.value == 2 and description.name.decoded:
            found.add(description.name.decoded)

    for collection_path, index in pools:
        if collection_path == "particles" and 0 <= index < len(resource.particles.items):
            for te in resource.particles.items[index].timed_effects.items:
                if te.effect_name.decoded:
                    found.add(te.effect_name.decoded)
        elif collection_path == "components.sequences" and 0 <= index < len(resource.components.sequences.items):
            for item in resource.components.sequences.items[index].items.items:
                if item.effect_name.decoded:
                    found.add(item.effect_name.decoded)
        elif collection_path == "dynamic_particles" and 0 <= index < len(resource.dynamic_particles.items):
            base = resource.dynamic_particles.items[index].base_name.decoded or ""
            if base:
                found.add(base)
    return found


def _effect_reference_order(
    resource: EffDirResource,
    starts: List[int],
    coverage: Coverage,
    *,
    unresolved_note_path: Optional[str],
) -> Tuple[List[int], Set[Tuple[str, int]]]:
    """Depth-first walk over effect -> effect references (chainEffect,
    timedEffect, visualEffect, sequence play, effectBase), starting from
    `starts`, in dependency order.

    Returns effect indices ordered so that every effect one of those
    references points at appears before the effect containing the
    reference, plus the union of every pool the walk reaches.
    `visualEffect` requires "referenced effect must already exist"
    (docs/reference/effect-children/visual-effect.md); the other reference
    kinds are not documented as requiring it, but ordering them the same
    way is free and keeps the source consistently declare-before-use,
    matching the pools-before-effects convention this module already
    follows.

    Cycles are safe: an effect already on the current DFS path is not
    re-entered, which necessarily leaves one edge of the cycle pointing
    forward -- no linear ordering can satisfy every edge of a cycle. That
    edge is reported as a coverage note so the gap is visible rather than
    silently producing a source file that may fail to load.

    When `unresolved_note_path` is given, names that resolve to nothing are
    reported against that path -- in a multi-resource setup they
    legitimately live in another EFFDIR (editor/references.py documents the
    same partial-resolution result against the real vanilla file), so they
    are a note, not an error.
    """

    by_name = _effect_indices_by_name(resource)
    order: List[int] = []
    visited: Set[int] = set()
    on_stack: Set[int] = set()
    pools: Set[Tuple[str, int]] = set()
    unresolved: Set[str] = set()
    forward_refs: List[Tuple[int, int]] = []

    def visit(index: int) -> None:
        if index in visited:
            return
        on_stack.add(index)
        current_pools = _referenced_pools(resource, index)
        pools.update(current_pools)
        for name in sorted(_effect_names_referenced_by(resource, index, current_pools)):
            targets = by_name.get(name.casefold())
            if not targets:
                unresolved.add(name)
                continue
            for target in targets:
                if not (0 <= target < len(resource.effect_descriptions.items)):
                    continue
                if target in on_stack:
                    forward_refs.append((index, target))
                elif target not in visited:
                    visit(target)
        on_stack.discard(index)
        visited.add(index)
        order.append(index)

    for start in starts:
        visit(start)

    if unresolved_note_path is not None:
        for name in sorted(unresolved):
            coverage.note(
                unresolved_note_path,
                "info",
                f"referenced effect {name!r} is not defined in this resource; it was not included in the closure "
                "(it presumably lives in another loaded EFFDIR)",
            )
    for referencing, referenced in forward_refs:
        coverage.note(
            f"effect_descriptions[{referencing}]",
            "info",
            f"effect_descriptions[{referenced}] and this effect reference each other in a cycle; "
            f"effect_descriptions[{referenced}] could not be emitted before this effect, so the exported source "
            "may fail to load until the two are reordered by hand",
        )
    return order, pools


def emit_effect_closure(
    resource: EffDirResource,
    effect_index: int,
    *,
    transitive: bool = False,
) -> Optional[FxEmitResult]:
    """Decompile one effect together with what it depends on.

    With `transitive=False` (default) this is one level deep: the effect
    itself, the particle/decal/dynamicParticle/sequence pools its own
    children point at, and the shake/light pools its own events point at.

    With `transitive=True` it also follows effect-to-effect references --
    `chainEffect`, `visualEffect`, a particle's `timedEffect`, a sequence's
    `play` items, and a dynamic particle's `effectBase` -- repeatedly, until
    nothing new is reachable, and emits every effect and pool found along
    the way. Cycles terminate safely.
    """

    if not (0 <= effect_index < len(resource.effect_descriptions.items)):
        return None

    coverage = Coverage()
    writer = FxWriter()
    writer.comment(_HEADER)
    writer.blank()

    names = resolve_names(resource, coverage)

    if transitive:
        effect_indices, wanted = _effect_reference_order(
            resource, [effect_index], coverage, unresolved_note_path=f"effect_descriptions[{effect_index}]"
        )
    else:
        effect_indices, wanted = [effect_index], _referenced_pools(resource, effect_index)

    _emit_inline_resource_ids(writer, coverage, resource, names, effect_indices)
    _emit_asset_ids(writer, resource, wanted)
    _emit_camera_params(writer, coverage, resource)

    # Two events may target the same shake or light (a flash and a tint
    # commonly share one light description), and in a transitive walk two
    # effects may target the same one. A pool block may only be defined
    # once in the output, so collect indices as a set before emitting.
    wanted_shakes: Set[int] = set()
    wanted_lights: Set[int] = set()
    for index in effect_indices:
        for e in resource.effect_descriptions.items[index].events.items:
            target = e.value.value
            if e.flags.value & (1 << 0) and 0 <= target < len(resource.shakes.items):
                wanted_shakes.add(target)
            if e.flags.value & ((1 << 2) | (1 << 3)) and 0 <= target < len(resource.lights.items):
                wanted_lights.add(target)

    for index, particle in enumerate(resource.particles.items):
        if ("particles", index) in wanted:
            note_non_finite_floats(particle, f"particles[{index}]", coverage)
            emit_particles(writer, coverage, names.by_collection[("particles", index)], particle, path=f"particles[{index}]")
            writer.blank()
    for index, decal in enumerate(resource.decals.items):
        if ("decals", index) in wanted:
            note_non_finite_floats(decal, f"decals[{index}]", coverage)
            emit_decal(writer, coverage, names.by_collection[("decals", index)], decal, path=f"decals[{index}]")
            writer.blank()
    for index in sorted(wanted_shakes):
        note_non_finite_floats(resource.shakes.items[index], f"shakes[{index}]", coverage)
        emit_shake(writer, coverage, names.shakes[index], resource.shakes.items[index], path=f"shakes[{index}]")
        writer.blank()
    for index in sorted(wanted_lights):
        note_non_finite_floats(resource.lights.items[index], f"lights[{index}]", coverage)
        emit_light(writer, coverage, names.lights[index], resource.lights.items[index], path=f"lights[{index}]")
        writer.blank()
    for index, dp in enumerate(resource.dynamic_particles.items):
        if ("dynamic_particles", index) in wanted:
            note_non_finite_floats(dp, f"dynamic_particles[{index}]", coverage)
            emit_dynamic_particle(writer, coverage, names.by_collection[("dynamic_particles", index)], dp, path=f"dynamic_particles[{index}]")
            writer.blank()
    for index, sequence in enumerate(resource.components.sequences.items):
        if ("components.sequences", index) in wanted:
            emit_sequence(writer, coverage, names.by_collection[("components.sequences", index)], sequence, path=f"components.sequences[{index}]")
            writer.blank()

    for index in effect_indices:
        effect = resource.effect_descriptions.items[index]
        note_non_finite_floats(effect, f"effect_descriptions[{index}]", coverage)
        aliases = [a for a in names.effect_names.get(index, []) if a] or [f"effect_{index}"]
        emit_effect(writer, coverage, resource, names, index, effect, aliases[0])
        writer.blank()

    return FxEmitResult(text=writer.text(), coverage=coverage)
