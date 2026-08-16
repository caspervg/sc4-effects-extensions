"""Name resolution pass: every named pool (`particles`, `decal`, `shake`,
`light`, `dynamicParticle`, and the five "anonymous" component families)
gets its canonical name from wherever it is *referenced*, not from the
pool record itself -- none of `ParticleDescriptor`, `DecalDescriptor`,
`DynamicParticleDescriptor`, `SequenceDescription`, `ShakeDescriptor`, or
`LightDescriptor` carries a name field of its own.

`DescriptionRecord.name` ("Source child name", effdir.md Section 12) is
that name for particle/decal/dynamic-particle/sequence children.
Brush and sound records instead retain only a numeric resource key; the
decompiler gives equal keys one canonical alias derived from the first named
effect that uses the key and declares it through `brushID`/`soundID`.
Attractors retain their actual source name in the component record itself.
`EventRecord.name` ("Source shake or light
description name") is that name for shake/light. A pool entry
that is never referenced by any effect is a real possibility (an author
can define more than they use) -- it gets a synthesized placeholder name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..editor.references import COMPONENT_COLLECTIONS, NAME_BASED_COMPONENT_TYPES
from ..model.resource import EffDirResource
from .coverage import Coverage

# component_type values with a confirmed fx-side "definition" story of
# their own (docs/reference/top-level/*.md): referenced by name from a
# child command, never redefined inline.
NAMED_POOL_TYPES = {0, 1, 6, 16}
# component_type values whose fx spelling embeds full fields directly on
# the child command instead (docs/reference/effect-children/*-effect.md:
# brushEffect, automataEffect, scrubberEffect, soundEffect, cameraEffect).
INLINE_TYPES = {3, 4, 5, 7, 8}


def _collection_len(resource: EffDirResource, collection_path: str) -> int:
    target = resource
    for token in collection_path.split("."):
        target = getattr(target, token)
    return len(target.items)


@dataclass
class ResolvedNames:
    # (collection_path, index) -> canonical name, for every component_type
    # in COMPONENT_COLLECTIONS (particles, decals, dynamic_particles,
    # components.sequences, components.brushes, components.attractors,
    # components.scrubbers, components.sounds, components.cameras).
    by_collection: Dict[Tuple[str, int], str] = field(default_factory=dict)
    # shakes[index] / lights[index] -> canonical name, from EventRecord.name.
    shakes: Dict[int, str] = field(default_factory=dict)
    lights: Dict[int, str] = field(default_factory=dict)
    # effect_descriptions index -> [name, ...alias names...], from
    # effect_name_map (editor/references.py's ReferenceIndex.names covers
    # only the first target; this keeps every alias for that index).
    effect_names: Dict[int, List[str]] = field(default_factory=dict)
    def name_for(self, component_type: int, index: int) -> str:
        collection = COMPONENT_COLLECTIONS.get(component_type)
        if collection is None:
            return f"unknown_component_{component_type}_{index}"
        return self.by_collection.get((collection[0], index), f"{collection[1]}_{index}")

def resolve_names(resource: EffDirResource, coverage: Coverage) -> ResolvedNames:
    resolved = ResolvedNames()

    for i, entry in enumerate(resource.effect_name_map.items):
        target = entry.target.value
        name = entry.name.decoded or ""
        resolved.effect_names.setdefault(target, []).append(name)

    for effect_index, effect in enumerate(resource.effect_descriptions.items):
        for description_index, description in enumerate(effect.descriptions.items):
            component_type = description.component_type.value
            index = description.description_index.value
            if component_type in NAME_BASED_COMPONENT_TYPES:
                continue
            collection = COMPONENT_COLLECTIONS.get(component_type)
            if collection is None:
                continue
            collection_path, _label = collection
            if index < 0 or index >= _collection_len(resource, collection_path):
                continue
            key = (collection_path, index)
            # These three families do not use DescriptionRecord.name for
            # their source identity. See _fill_intrinsic_component_names.
            name = "" if component_type in (3, 4, 7) else (description.name.decoded or "")
            if name and key not in resolved.by_collection:
                resolved.by_collection[key] = name

        for event in effect.events.items:
            flags = event.flags.value
            index = event.value.value
            name = event.name.decoded or ""
            if not name:
                continue
            if flags & (1 << 0) and 0 <= index < len(resource.shakes.items):
                resolved.shakes.setdefault(index, name)
            if flags & ((1 << 2) | (1 << 3)) and 0 <= index < len(resource.lights.items):
                resolved.lights.setdefault(index, name)

    _fill_intrinsic_component_names(resource, resolved)
    _fill_orphans(resource, resolved, coverage)
    return resolved


def _resource_key_owners(resource: EffDirResource, resolved: ResolvedNames, component_type: int) -> Dict[int, str]:
    """Numeric resource key -> first named effect which references it."""

    owners: Dict[int, str] = {}
    for effect_index, effect in enumerate(resource.effect_descriptions.items):
        owner = next((name for name in resolved.effect_names.get(effect_index, []) if name), "")
        if not owner:
            continue
        for description in effect.descriptions.items:
            if description.component_type.value != component_type:
                continue
            index = description.description_index.value
            if component_type == 3 and 0 <= index < len(resource.components.brushes.items):
                key = resource.components.brushes.items[index].key.value
            elif component_type == 7 and 0 <= index < len(resource.components.sounds.items):
                key = resource.components.sounds.items[index].resource_key.value
            else:
                continue
            owners.setdefault(key, owner)
    return owners


def _key_aliases(keys: List[int], owners: Dict[int, str], label: str) -> Dict[int, str]:
    """Assign one unique, deterministic alias to every distinct key."""

    aliases: Dict[int, str] = {}
    used: set[str] = set()
    for index, key in enumerate(keys):
        if key in aliases:
            continue
        owner = owners.get(key)
        base = f"{owner}_{label}" if owner else f"{label}_{index}"
        alias = base
        suffix = 2
        while alias.casefold() in used:
            alias = f"{base}_{suffix}"
            suffix += 1
        aliases[key] = alias
        used.add(alias.casefold())
    return aliases


def _fill_intrinsic_component_names(resource: EffDirResource, resolved: ResolvedNames) -> None:
    """Recover names whose identity is stored outside DescriptionRecord.

    The two ID maps are not serialized in EFFDIR. Their numeric values are,
    so deterministic aliases restore valid source without pretending to
    recover the author's original spelling. Equal keys deliberately share
    one alias and therefore one ID declaration.
    """

    brush_keys = [brush.key.value for brush in resource.components.brushes.items]
    brush_aliases = _key_aliases(brush_keys, _resource_key_owners(resource, resolved, 3), "brush")
    for index, brush in enumerate(resource.components.brushes.items):
        resolved.by_collection[("components.brushes", index)] = brush_aliases[brush.key.value]

    for index, attractor in enumerate(resource.components.attractors.items):
        name = attractor.name.decoded or ""
        if name:
            resolved.by_collection[("components.attractors", index)] = name

    sound_keys = [sound.resource_key.value for sound in resource.components.sounds.items]
    sound_aliases = _key_aliases(sound_keys, _resource_key_owners(resource, resolved, 7), "sound")
    for index, sound in enumerate(resource.components.sounds.items):
        resolved.by_collection[("components.sounds", index)] = sound_aliases[sound.resource_key.value]


def _fill_orphans(resource: EffDirResource, resolved: ResolvedNames, coverage: Coverage) -> None:
    for component_type, (collection_path, label) in COMPONENT_COLLECTIONS.items():
        count = _collection_len(resource, collection_path)
        for index in range(count):
            key = (collection_path, index)
            if key in resolved.by_collection:
                continue
            synthesized = f"{label.replace(' ', '_')}_{index}"
            resolved.by_collection[key] = synthesized

    for index in range(len(resource.shakes.items)):
        if index in resolved.shakes:
            continue
        synthesized = f"shake_{index}"
        resolved.shakes[index] = synthesized

    for index in range(len(resource.lights.items)):
        if index in resolved.lights:
            continue
        synthesized = f"light_{index}"
        resolved.lights[index] = synthesized
