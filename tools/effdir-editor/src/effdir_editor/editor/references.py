"""Cross-reference index: which top-level lookup entries point at a given
`effect_descriptions[i]` record.

Verified against the real vanilla `EFFDIR` in `SimCity_1.dat`: contrary to
what effdir.md's prose implies ("effect-name lookup map"),
`effect_name_map[i].target` is not matched against `EffectDescription.
effect_name` -- that field reads back empty (0-length string) for every one
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

What is *not* built here: a backlink from a `ParticleDescriptor`/
`DecalDescriptor`/`ShakeDescriptor`/`LightDescriptor` to the effects that
use it. Those records carry no name field at all, and the field that would
establish the join -- `DescriptionRecord.mode`/`.name` inside an effect's
own `descriptions` vector (model/effect.py) -- has no resolved semantics
yet (type selector? positional index? something else?) per effdir.md.
Wiring that up without guessing needs another reverse-engineering pass.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

from ..model.resource import EffDirResource


@dataclass(frozen=True)
class Reference:
    path: str
    label: str


@dataclass(frozen=True)
class ReferenceIndex:
    backlinks: Dict[int, List[Reference]]  # effect_descriptions index -> what names it
    names: Dict[int, str]  # effect_descriptions index -> its name, from effect_name_map


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
    return references


def build_reference_index(resource: EffDirResource) -> ReferenceIndex:
    """Maps an `effect_descriptions` index to the entries that name it."""

    name_to_indices: Dict[str, List[int]] = defaultdict(list)
    for entry in resource.effect_name_map.items:
        name_to_indices[entry.name.decoded].append(entry.target.value)
    names: Dict[int, str] = {entry.target.value: entry.name.decoded for entry in resource.effect_name_map.items}

    index: Dict[int, List[Reference]] = defaultdict(list)
    for i, entry in enumerate(resource.effect_name_map.items):
        index[entry.target.value].append(
            Reference(path=f"effect_name_map[{i}]", label=f'effect_name_map[{i}] "{entry.name.decoded}"')
        )
    for i, entry in enumerate(resource.effect_key_map.items):
        for target in name_to_indices.get(entry.name.decoded, []):
            index[target].append(
                Reference(
                    path=f"effect_key_map[{i}]",
                    label=(
                        f'effect_key_map[{i}] "{entry.name.decoded}" '
                        f"(group 0x{entry.group_id.value:08X}, instance 0x{entry.instance_id.value:08X})"
                    ),
                )
            )
    for i, trigger in enumerate(resource.message_triggers.items):
        for target in name_to_indices.get(trigger.effect_name.decoded, []):
            index[target].append(
                Reference(
                    path=f"message_triggers[{i}]",
                    label=f'message_triggers[{i}] "{trigger.effect_name.decoded}" (message 0x{trigger.message_id.value:08X})',
                )
            )
    for i, sequence in enumerate(resource.components.sequences.items):
        for j, item in enumerate(sequence.items.items):
            if not item.effect_name.decoded:
                continue  # a "wait" item has no effect name; only "play" items reference one
            for target in name_to_indices.get(item.effect_name.decoded, []):
                index[target].append(
                    Reference(
                        path=f"components.sequences[{i}].items[{j}]",
                        label=(
                            f'components.sequences[{i}].items[{j}] "{item.effect_name.decoded}" '
                            f"(play, timing {item.timing.x:g}/{item.timing.y:g})"
                        ),
                    )
                )
    return ReferenceIndex(backlinks=dict(index), names=names)
