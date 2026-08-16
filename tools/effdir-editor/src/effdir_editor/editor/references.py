"""Cross-reference index for known EFFDIR links.

Verified against the real vanilla `EFFDIR` in `SimCity_1.dat`: contrary to
what effdir.md's prose implies ("effect-name lookup map"),
`effect_name_map[i].target` is not matched against `EffectDescription.
chain_effect` -- that field reads back empty (0-length string) for every one
of the file's 1154 effect descriptions. Instead `target` is a plain index
into `effect_descriptions.items` (the 1154 target values in the real file
are exactly the permutation `0..1153`, one per description, all unique).
So `effect_name_map` is the *only* place an effect's name actually lives;
everything else that wants to reference an effect by name --
`effect_key_map`, `message_triggers`, and each `SequenceDescription`'s
`play`-command `SequenceItem.effect_name` -- must resolve through
`effect_name_map` first, by string, and then follow its `target` as an
index. Checked against the real file: 67/82 key-map entries, 2/2 message
triggers, and 31/34 sequence `play` items resolve this way; the remainder
presumably name effects defined in a different EFFDIR resource, which this
single-resource index can't see.

Event records are the exception among component references: their final u32
is proven by `StartAncilliary` to index top-level `shakes` for bit 0 and
`lights` for bits 2/3. Those direct references are included as
path-based backlinks. DescriptionRecord component references use the
component-type values observed in the vanilla resource to link into the
corresponding top-level collection. Component type 2 is the exception: it is
a name-based `visualEffect` link and its index is not a collection index.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import re
from typing import Dict, List

from ..model.resource import EffDirResource


@dataclass(frozen=True)
class Reference:
    path: str
    label: str
    kind: str = ""


def reference_kind(reference: Reference) -> str:
    """Return a short UI category for a known reference."""

    if reference.kind:
        return reference.kind
    path = reference.path
    if path.startswith("effect_name_map"):
        return "Effect name"
    if path.startswith("effect_key_map"):
        return "Effect key"
    if path.startswith("message_triggers"):
        return "Message trigger"
    if path.startswith("components.sequences"):
        return "Sequence"
    if ".descriptions[" in path:
        return "Component"
    if ".events[" in path:
        return "Event"
    return "Reference"


def reference_info(reference: Reference) -> str:
    """Return reference context without repeating its source path."""

    label = reference.label.strip()
    if label.startswith(reference.path):
        return label[len(reference.path) :].strip()

    match = re.fullmatch(
        r"(effect_descriptions\[\d+\])\.(descriptions|events)\[(\d+)\]",
        reference.path,
    )
    if match and label.startswith(match.group(1)):
        owner = label[len(match.group(1)) :].strip()
        marker = f"{match.group(2)[:-1]}[{match.group(3)}]"
        if marker in owner:
            owner_name, child = owner.split(marker, 1)
            owner_name = owner_name.strip()
            child = child.strip()
            return f"effect {owner_name} · {match.group(2)[:-1]} {child}".strip()

    return label


# tSC4ComponentEffectType values confirmed by the vanilla EFFDIR's
# DescriptionRecord indices and collection sizes. Keep this table here so
# navigation and validation share the same evidence-backed mapping.
COMPONENT_COLLECTIONS = {
    0: ("particles", "particle"),
    1: ("decals", "decal"),
    3: ("components.brushes", "brush"),
    4: ("components.attractors", "attractor"),
    5: ("components.scrubbers", "scrubber"),
    6: ("components.sequences", "sequence"),
    7: ("components.sounds", "sound"),
    8: ("components.cameras", "camera"),
    16: ("dynamic_particles", "dynamic particle"),
}

NAME_BASED_COMPONENT_TYPES = {2}


@dataclass(frozen=True)
class ReferenceIndex:
    backlinks: Dict[int, List[Reference]]  # effect_descriptions index -> what names it
    names: Dict[int, str]  # effect_descriptions index -> its name, from effect_name_map
    path_backlinks: Dict[str, List[Reference]] = field(default_factory=dict)
    outgoing: Dict[str, List[Reference]] = field(default_factory=dict)


def references_to_name(resource: EffDirResource, name: str) -> List[Reference]:
    """Return name-based consumers that would break if an alias vanished."""

    references: List[Reference] = []
    for i, entry in enumerate(resource.effect_key_map.items):
        if entry.name.decoded == name:
            references.append(
                Reference(
                    path=f"effect_key_map[{i}]",
                    label=(
                        f'effect_key_map[{i}] "{name}" '
                        f"(group 0x{entry.group_id.value:08X}, instance 0x{entry.instance_id.value:08X})"
                    ),
                )
            )
    for i, trigger in enumerate(resource.message_triggers.items):
        if trigger.effect_name.decoded == name:
            references.append(
                Reference(
                    path=f"message_triggers[{i}]",
                    label=f'message_triggers[{i}] "{name}" (message 0x{trigger.message_id.value:08X})',
                )
            )
    for i, sequence in enumerate(resource.components.sequences.items):
        for j, item in enumerate(sequence.items.items):
            if item.effect_name.decoded == name:
                references.append(
                    Reference(
                        path=f"components.sequences[{i}].items[{j}]",
                        label=(
                            f'components.sequences[{i}].items[{j}] "{name}" '
                            f"(play, timing {item.timing.x:g}/{item.timing.y:g})"
                        ),
                    )
                )
    for effect_index, effect in enumerate(resource.effect_descriptions.items):
        descriptions = getattr(effect, "descriptions", None)
        if descriptions is None:
            continue
        for description_index, description in enumerate(descriptions.items):
            if int(description.component_type.value) == 2 and description.name.decoded == name:
                source_path = f"effect_descriptions[{effect_index}].descriptions[{description_index}]"
                references.append(
                    Reference(path=source_path, label=f'{source_path} "{name}" (visualEffect)')
                )
    return references


def build_reference_index(resource: EffDirResource) -> ReferenceIndex:
    """Build known incoming and outgoing links without guessing unknown ones."""

    name_to_indices: Dict[str, List[int]] = defaultdict(list)
    for entry in resource.effect_name_map.items:
        name_to_indices[entry.name.decoded.casefold()].append(entry.target.value)
    names: Dict[int, str] = {entry.target.value: entry.name.decoded for entry in resource.effect_name_map.items}

    index: Dict[int, List[Reference]] = defaultdict(list)
    outgoing: Dict[str, List[Reference]] = defaultdict(list)

    def add_outgoing(source_path: str, target_path: str, label: str, kind: str) -> None:
        outgoing[source_path].append(Reference(target_path, label, kind))

    for i, entry in enumerate(resource.effect_name_map.items):
        source_path = f"effect_name_map[{i}]"
        target_path = f"effect_descriptions[{entry.target.value}]"
        index[entry.target.value].append(
            Reference(path=source_path, label=f'{source_path} "{entry.name.decoded}"')
        )
        add_outgoing(source_path, target_path, f'effect "{entry.name.decoded}"', "Effect name")
    for i, entry in enumerate(resource.effect_key_map.items):
        source_path = f"effect_key_map[{i}]"
        for target in name_to_indices.get(entry.name.decoded.casefold(), []):
            target_path = f"effect_descriptions[{target}]"
            index[target].append(
                Reference(
                    path=source_path,
                    label=(
                        f'{source_path} "{entry.name.decoded}" '
                        f"(group 0x{entry.group_id.value:08X}, instance 0x{entry.instance_id.value:08X})"
                    ),
                )
            )
            add_outgoing(
                source_path,
                target_path,
                f'effect "{entry.name.decoded}" '
                f"(group 0x{entry.group_id.value:08X}, instance 0x{entry.instance_id.value:08X})",
                "Effect key",
            )
    for i, trigger in enumerate(resource.message_triggers.items):
        source_path = f"message_triggers[{i}]"
        for target in name_to_indices.get(trigger.effect_name.decoded.casefold(), []):
            target_path = f"effect_descriptions[{target}]"
            index[target].append(
                Reference(
                    path=source_path,
                    label=f'{source_path} "{trigger.effect_name.decoded}" (message 0x{trigger.message_id.value:08X})',
                )
            )
            add_outgoing(
                source_path,
                target_path,
                f'effect "{trigger.effect_name.decoded}" (message 0x{trigger.message_id.value:08X})',
                "Message trigger",
            )
    for i, sequence in enumerate(resource.components.sequences.items):
        for j, item in enumerate(sequence.items.items):
            if not item.effect_name.decoded:
                continue  # a "wait" item has no effect name; only "play" items reference one
            source_path = f"components.sequences[{i}].items[{j}]"
            for target in name_to_indices.get(item.effect_name.decoded.casefold(), []):
                target_path = f"effect_descriptions[{target}]"
                index[target].append(
                    Reference(
                        path=source_path,
                        label=(
                            f'{source_path} "{item.effect_name.decoded}" '
                            f"(play, timing {item.timing.x:g}/{item.timing.y:g})"
                        ),
                    )
                )
                add_outgoing(
                    source_path,
                    target_path,
                    f'effect "{item.effect_name.decoded}" '
                    f"(play, timing {item.timing.x:g}/{item.timing.y:g})",
                    "Sequence",
                )
    for effect_index, effect in enumerate(resource.effect_descriptions.items):
        descriptions = getattr(effect, "descriptions", None)
        if descriptions is None:
            continue
        for description_index, description in enumerate(descriptions.items):
            if int(description.component_type.value) != 2:
                continue
            name = description.name.decoded or ""
            source_path = f"effect_descriptions[{effect_index}].descriptions[{description_index}]"
            for target in name_to_indices.get(name.casefold(), []):
                target_path = f"effect_descriptions[{target}]"
                index[target].append(
                    Reference(source_path, f'{source_path} "{name}" (visualEffect)')
                )
                add_outgoing(source_path, target_path, f'visualEffect "{name}"', "Component")
                add_outgoing(
                    f"effect_descriptions[{effect_index}]",
                    target_path,
                    f'description[{description_index}] → visualEffect "{name}"',
                    "Component",
                )
    path_backlinks: Dict[str, List[Reference]] = {
        f"effect_descriptions[{target}]": references
        for target, references in index.items()
    }
    shake_count = len(resource.shakes.items)
    light_count = len(resource.lights.items)
    for effect_index, effect in enumerate(resource.effect_descriptions.items):
        effect_name = names.get(effect_index, "")
        owner_path = f'effect_descriptions[{effect_index}]'
        owner = owner_path
        if effect_name:
            owner += f' "{effect_name}"'
        for event_index, event in enumerate(effect.events.items):
            flags = int(event.flags.value)
            target = int(event.value.value)
            source_path = f"effect_descriptions[{effect_index}].events[{event_index}]"
            event_name = event.name.decoded
            if flags & 1 and 0 <= target < shake_count:
                target_path = f"shakes[{target}]"
                path_backlinks.setdefault(target_path, []).append(
                    Reference(source_path, f'{owner} event[{event_index}] "{event_name}" (shakeEffect)')
                )
                add_outgoing(source_path, target_path, f'shakeEffect "{event_name}"', "Event")
                add_outgoing(owner_path, target_path, f'event[{event_index}] → shakeEffect "{event_name}"', "Event")
            if flags & (1 << 2) and 0 <= target < light_count:
                target_path = f"lights[{target}]"
                path_backlinks.setdefault(target_path, []).append(
                    Reference(source_path, f'{owner} event[{event_index}] "{event_name}" (flashEffect)')
                )
                add_outgoing(source_path, target_path, f'flashEffect "{event_name}"', "Event")
                add_outgoing(owner_path, target_path, f'event[{event_index}] → flashEffect "{event_name}"', "Event")
            if flags & (1 << 3) and 0 <= target < light_count:
                target_path = f"lights[{target}]"
                path_backlinks.setdefault(target_path, []).append(
                    Reference(source_path, f'{owner} event[{event_index}] "{event_name}" (tintEffect)')
                )
                add_outgoing(source_path, target_path, f'tintEffect "{event_name}"', "Event")
                add_outgoing(owner_path, target_path, f'event[{event_index}] → tintEffect "{event_name}"', "Event")
        descriptions = getattr(effect, "descriptions", None)
        if descriptions is None:
            continue
        for description_index, description in enumerate(descriptions.items):
            if int(description.component_type.value) in NAME_BASED_COMPONENT_TYPES:
                continue
            component = COMPONENT_COLLECTIONS.get(description.component_type.value)
            if component is None:
                continue
            collection_path, component_label = component
            target = int(description.description_index.value)
            collection = resource
            for token in collection_path.split("."):
                collection = getattr(collection, token)
            if not 0 <= target < len(collection.items):
                continue
            source_path = f"effect_descriptions[{effect_index}].descriptions[{description_index}]"
            description_name = description.name.decoded or ""
            target_path = f"{collection_path}[{target}]"
            path_backlinks.setdefault(target_path, []).append(
                Reference(
                    source_path,
                    f'{owner} description[{description_index}] "{description_name}" ({component_label})',
                )
            )
            add_outgoing(
                source_path,
                target_path,
                f'{component_label} "{description_name}"'.strip(),
                "Component",
            )
            add_outgoing(
                owner_path,
                target_path,
                f'description[{description_index}] → {component_label} "{description_name}"'.strip(),
                "Component",
            )
    return ReferenceIndex(
        backlinks=dict(index),
        names=names,
        path_backlinks=path_backlinks,
        outgoing=dict(outgoing),
    )
