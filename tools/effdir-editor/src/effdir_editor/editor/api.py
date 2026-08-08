"""Headless editor API (effdir-editor-spec.md, "Core/editor API"). The UI
is one client of this module; agents can call the same functions. Note:
`open()` intentionally shadows the builtin within this module's namespace
per the spec's naming -- import this module qualified
(`from effdir_editor.editor import api`), not with `from ... import *`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..container.adapter import EffDirSource, ResourceHandle, WriteOptions
from ..model.components import default_attractor, default_brush, default_camera, default_scrubber, default_sequence, default_sound
from ..model.decal import default_decal
from ..model.dynamic_particle import default_dynamic_particle
from ..model.effect import default_effect_description
from ..model.light import default_light
from ..model.particle import default_particle
from ..model.resource import write_resource
from ..model.shake import default_shake
from ..wire import Diagnostic, Raw, WireString
from . import nodes as _nodes
from . import paths as _paths
from .session import Change, ChangeSet, EditorSession, open_session

RECORD_FACTORIES: Dict[str, Any] = {
    "ParticleDescriptor": default_particle,
    "DecalDescriptor": default_decal,
    "ShakeDescriptor": default_shake,
    "LightDescriptor": default_light,
    "DynamicParticleDescriptor": default_dynamic_particle,
    "EffectDescription": default_effect_description,
    "BrushDescription": default_brush,
    "AttractorDescription": default_attractor,
    "ScrubberDescription": default_scrubber,
    "SequenceDescription": default_sequence,
    "SoundDescription": default_sound,
    "CameraDescription": default_camera,
}


@dataclass(frozen=True)
class ResourceSummary:
    tgi: str
    major: int
    minor: int
    counts: Dict[str, int]
    dirty: bool


@dataclass(frozen=True)
class WritePreview:
    changed_paths: List[str]
    output_size: int
    unknown_bytes_preserved: bool
    diagnostics: List[Diagnostic]


@dataclass(frozen=True)
class CommitResult:
    output_path: str
    backup_path: Optional[str]
    diagnostics: List[Diagnostic]


def open(source: EffDirSource, handle: ResourceHandle) -> EditorSession:
    return open_session(source, handle)


def inspect(session: EditorSession) -> ResourceSummary:
    r = session.working
    counts = {
        "particles": len(r.particles.items),
        "decals": len(r.decals.items),
        "shakes": len(r.shakes.items),
        "lights": len(r.lights.items),
        "brushes": len(r.components.brushes.items),
        "attractors": len(r.components.attractors.items),
        "scrubbers": len(r.components.scrubbers.items),
        "sequences": len(r.components.sequences.items),
        "sounds": len(r.components.sounds.items),
        "cameras": len(r.components.cameras.items),
        "dynamic_particles": len(r.dynamic_particles.items),
        "effect_descriptions": len(r.effect_descriptions.items),
        "message_triggers": len(r.message_triggers.items),
    }
    return ResourceSummary(
        tgi=session.handle.tgi,
        major=r.version.major.value,
        minor=r.version.minor.value,
        counts=counts,
        dirty=session.dirty,
    )


def list_nodes(session: EditorSession, path: Optional[str]) -> List[_nodes.NodeSummary]:
    base = path or ""
    dirty = session.dirty_paths
    return [_nodes.build_node(session.working, p, dirty_paths=dirty).summary for p in _nodes.child_paths(session.working, base)]


def get_node(session: EditorSession, path: str) -> _nodes.Node:
    return _nodes.build_node(session.working, path, dirty_paths=session.dirty_paths)


def set_raw(session: EditorSession, path: str, new_value: Any) -> ChangeSet:
    node = get_node(session, path)
    target = _paths.get_path(session.working, path)
    kind = _nodes.classify(target)

    if kind == "scalar" and isinstance(target, Raw):
        updated = target.replace(new_value)
    elif kind == "string" and isinstance(target, WireString):
        updated = WireString.from_text(new_value) if isinstance(new_value, str) else WireString.from_raw_bytes(bytes(new_value))
    else:
        # Unwrapped vector element (plain float/int/str) -- no Raw/WireString
        # wrapper to preserve, just replace the value directly.
        updated = new_value

    before = node.raw.value if node.raw is not None else node.value
    session.snapshot()
    _paths.set_path(session.working, path, updated)
    change = session.record_change(path, before=before, after=new_value, reason="user")
    return ChangeSet(changes=[change], diagnostics=[])


def add_record(session: EditorSession, collection_path: str, record_type: str) -> ChangeSet:
    factory = RECORD_FACTORIES.get(record_type)
    if factory is None:
        raise ValueError(f"no default-record factory registered for {record_type!r}")
    session.snapshot()
    collection = _paths.get_path(session.working, collection_path)
    new_record = factory()
    collection.items.append(new_record)
    path = f"{collection_path}[{len(collection.items) - 1}]"
    change = session.record_change(path, before=None, after=new_record, reason="allocation")
    return ChangeSet(changes=[change], diagnostics=[])


def remove_record(session: EditorSession, record_path: str) -> ChangeSet:
    parent, key = _paths.get_parent_and_key(session.working, record_path)
    if not isinstance(key, int):
        raise ValueError(f"remove_record path must end in an index, got {record_path!r}")
    session.snapshot()
    removed = parent.items.pop(key)
    change = session.record_change(record_path, before=removed, after=None, reason="user")
    return ChangeSet(changes=[change], diagnostics=[])


def add_effect(session: EditorSession, name: str) -> ChangeSet:
    """Allocates an EffectDescription and its effect-name lookup entry
    together (effdir-editor-spec.md, "Add an effect description"). The
    map target is left at 0 -- an explicit editable integer, per spec,
    since target-allocation semantics are not independently confirmed."""

    session.snapshot()
    description = default_effect_description()
    description.effect_name = WireString.from_text(name)
    session.working.effect_descriptions.items.append(description)
    effect_index = len(session.working.effect_descriptions.items) - 1

    from ..model.common import StringU32Pair
    from ..wire import make_raw_u32

    session.working.effect_name_map.items.append(StringU32Pair(name=WireString.from_text(name), target=make_raw_u32(0)))
    map_index = len(session.working.effect_name_map.items) - 1

    change = session.record_change(
        f"effect_descriptions[{effect_index}]",
        before=None,
        after=description,
        reason="allocation",
        warnings=[f"effect_name_map[{map_index}].target left at 0; set it explicitly"],
    )
    return ChangeSet(changes=[change], diagnostics=[])


def validate(session: EditorSession) -> List[Diagnostic]:
    return list(session.working.preservation.diagnostics)


def preview_write(session: EditorSession) -> WritePreview:
    data = write_resource(session.working)
    return WritePreview(
        changed_paths=[c.path for c in session.change_log],
        output_size=len(data),
        unknown_bytes_preserved=True,
        diagnostics=validate(session),
    )


def commit(session: EditorSession, write_options: Optional[WriteOptions] = None) -> CommitResult:
    write_options = write_options or WriteOptions()
    backup_path = session.source.backup(session.handle)
    data = write_resource(session.working)
    result = session.source.write(session.handle, data, write_options)
    session.undo_stack.clear()
    session.redo_stack.clear()
    session.change_log.clear()
    return CommitResult(output_path=result.path, backup_path=backup_path, diagnostics=validate(session))


def undo(session: EditorSession) -> ChangeSet:
    session.undo()
    return ChangeSet(changes=[], diagnostics=[])


def redo(session: EditorSession) -> ChangeSet:
    session.redo()
    return ChangeSet(changes=[], diagnostics=[])
