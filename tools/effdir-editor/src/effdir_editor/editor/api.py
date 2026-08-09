"""Headless editor API (effdir-editor-spec.md, "Core/editor API"). The UI
is one client of this module; agents can call the same functions. Note:
`open()` intentionally shadows the builtin within this module's namespace
per the spec's naming -- import this module qualified
(`from effdir_editor.editor import api`), not with `from ... import *`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

from ..bindings.catalog import CATALOG, CommandBinding, Transform, find_by_id
from ..container.adapter import EffDirSource, ResourceHandle, WriteOptions
from ..model.components import (
    default_attractor,
    default_brush,
    default_camera,
    default_scrubber,
    default_sequence,
    default_sound,
)
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
from .opaque_ranges import opaque_ranges as _opaque_ranges
from .references import Reference, ReferenceIndex, build_reference_index, references_to_name
from .session import Change, ChangeSet, EditorSession, open_session
from .validation import validate_resource

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


class ReferenceIntegrityError(ValueError):
    def __init__(self, path: str, references: List[Reference]):
        self.path = path
        self.references = references
        super().__init__(f"cannot remove {path}; {len(references)} reference(s) would become dangling")


class CommandBindingError(ValueError):
    pass


class EvidenceConfirmationRequired(CommandBindingError):
    pass


class CommandConflictError(CommandBindingError):
    pass


class ValidationError(ValueError):
    def __init__(self, diagnostics: List[Diagnostic]):
        self.diagnostics = diagnostics
        summary = "; ".join(d.message for d in diagnostics[:3])
        if len(diagnostics) > 3:
            summary += f"; and {len(diagnostics) - 3} more"
        super().__init__(f"cannot write resource: {summary}")


_COMMAND_MEMBER_ALIASES = {
    ("ParticleDescriptor", "leading_bitset"): "flags_0",
    ("ParticleDescriptor", "second_bitset"): "flags_1",
    ("ParticleDescriptor", "third_bitset"): "flags_2",
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
    warnings: tuple[str, ...] = ()


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
    ref_index = build_reference_index(session.working)
    return [
        _nodes.build_node(session.working, p, dirty_paths=dirty, reference_index=ref_index).summary
        for p in _nodes.child_paths(session.working, base)
    ]


def get_node(
    session: EditorSession,
    path: str,
    *,
    reference_index: Optional[ReferenceIndex] = None,
) -> _nodes.Node:
    ref_index = reference_index
    if ref_index is None:
        ref_index = build_reference_index(session.working)
    return _nodes.build_node(session.working, path, dirty_paths=session.dirty_paths, reference_index=ref_index)


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


def set_command(
    session: EditorSession,
    command_path: str,
    new_value: Any,
    *,
    confirm_parser: bool = False,
    resolve_conflicts: bool = False,
) -> ChangeSet:
    record_path, bindings = _resolve_command(session, command_path)
    if any(binding.evidence in ("parser", "inferred") for binding in bindings) and not confirm_parser:
        ids = ", ".join(binding.id for binding in bindings)
        raise EvidenceConfirmationRequired(f"{ids} requires explicit parser-evidence confirmation")

    member_paths = list(dict.fromkeys(path for binding in bindings for path in binding.member_paths))
    values = _command_member_values(member_paths, new_value)
    pending: Dict[str, Any] = {}
    warnings: List[str] = []

    for binding in bindings:
        binding_values = {path: values[path] for path in binding.member_paths}
        _apply_command_transforms(binding, binding_values)
        values.update(binding_values)

    enabling = new_value is not None and (bool(new_value) or bool(member_paths))
    if enabling:
        for binding in bindings:
            for conflict_id in binding.conflicts:
                conflict = find_by_id(conflict_id)
                if conflict is None:
                    raise CommandBindingError(f"catalog conflict {conflict_id!r} does not exist")
                activity_known, active_bits = _active_presence_bits(session, record_path, conflict)
                if not activity_known:
                    warnings.append(f"shared storage may replace {conflict_id}")
                elif active_bits:
                    if not resolve_conflicts:
                        raise CommandConflictError(f"{binding.id} conflicts with active command {conflict_id}")
                    for bit_path, bit in active_bits:
                        _queue_bit_write(session, pending, bit_path, bit, False)

    for member_path, value in values.items():
        model_member = _command_member_name(bindings[0].record_type, member_path)
        full_path = f"{record_path}.{model_member}"
        target = _paths.get_path(session.working, full_path)
        pending[full_path] = _updated_value(target, value)

    for binding in bindings:
        bit_value = bool(new_value) if not binding.member_paths else new_value is not None
        for bit_ref in binding.presence_bits:
            model_member = _command_member_name(binding.record_type, bit_ref.member_path)
            _queue_bit_write(session, pending, f"{record_path}.{model_member}", bit_ref.bit, bit_value)

    if not pending:
        raise CommandBindingError(f"command {command_path!r} has no writable members or presence bits")

    session.snapshot()
    changes: List[Change] = []
    for path, updated in pending.items():
        before_target = _paths.get_path(session.working, path)
        before = before_target.value if isinstance(before_target, Raw) else before_target
        after = updated.value if isinstance(updated, Raw) else updated
        _paths.set_path(session.working, path, updated)
        changes.append(session.record_change(path, before, after, reason="binding", warnings=list(warnings)))
    return ChangeSet(changes=changes, diagnostics=[])


def _resolve_command(session: EditorSession, command_path: str) -> tuple[str, List[CommandBinding]]:
    matches: List[tuple[str, CommandBinding]] = []
    for binding in CATALOG:
        suffix = f".{binding.command_path}"
        if not command_path.endswith(suffix):
            continue
        record_path = command_path[: -len(suffix)]
        try:
            record = _paths.get_path(session.working, record_path)
        except (AttributeError, IndexError, KeyError, ValueError):
            continue
        if type(record).__name__ == binding.record_type:
            matches.append((record_path, binding))
    if not matches:
        raise CommandBindingError(f"no binding matches {command_path!r}")
    record_paths = {record_path for record_path, _ in matches}
    if len(record_paths) != 1:
        raise CommandBindingError(f"ambiguous record path for {command_path!r}")
    return matches[0][0], [binding for _, binding in matches]


def _command_member_values(member_paths: List[str], new_value: Any) -> Dict[str, Any]:
    if not member_paths or new_value is None:
        return {}
    if len(member_paths) == 1:
        return {member_paths[0]: new_value}
    if isinstance(new_value, dict):
        missing = [path for path in member_paths if path not in new_value]
        if missing:
            raise CommandBindingError(f"command value is missing members: {', '.join(missing)}")
        return {path: new_value[path] for path in member_paths}
    if isinstance(new_value, (list, tuple)) and len(new_value) == len(member_paths):
        return dict(zip(member_paths, new_value))
    raise CommandBindingError(f"command requires values for: {', '.join(member_paths)}")


def _command_member_name(record_type: str, member_path: str) -> str:
    return _COMMAND_MEMBER_ALIASES.get((record_type, member_path), member_path)


def _updated_value(target: Any, value: Any) -> Any:
    if isinstance(target, Raw):
        return target.replace(value)
    if isinstance(target, WireString):
        return WireString.from_text(value) if isinstance(value, str) else WireString.from_raw_bytes(bytes(value))
    return value


def _queue_bit_write(
    session: EditorSession,
    pending: Dict[str, Any],
    path: str,
    bit: int,
    enabled: bool,
) -> None:
    target = pending.get(path, _paths.get_path(session.working, path))
    if not isinstance(target, Raw):
        raise CommandBindingError(f"presence-bit member {path!r} is not raw storage")
    value = int(target.value)
    value = value | (1 << bit) if enabled else value & ~(1 << bit)
    pending[path] = target.replace(value)


def _active_presence_bits(
    session: EditorSession,
    record_path: str,
    binding: CommandBinding,
) -> Tuple[bool, List[Tuple[str, int]]]:
    if not binding.presence_bits:
        return False, []
    bits: List[tuple[str, int]] = []
    for bit_ref in binding.presence_bits:
        member = _command_member_name(binding.record_type, bit_ref.member_path)
        path = f"{record_path}.{member}"
        raw = _paths.get_path(session.working, path)
        if not isinstance(raw, Raw) or not int(raw.value) & (1 << bit_ref.bit):
            return True, []
        bits.append((path, bit_ref.bit))
    return True, bits


def _apply_command_transforms(binding: CommandBinding, values: Dict[str, Any]) -> None:
    for transform in binding.transforms:
        implementation = transform.implementation if isinstance(transform, Transform) else transform
        if implementation == "clamp":
            for path in values:
                values[path] = max(0.0, min(1.0, values[path]))
        elif implementation == "scale_by(50)":
            for path in values:
                values[path] = _scale_command_value(values[path], 50.0)
        elif implementation == "clamp(fade, max=length)":
            if "length" in values and "fade" in values:
                values["fade"] = min(values["fade"], values["length"])
        elif implementation == "optional geometry offset rounded to nearest integer":
            if "shell_offset" in values and values["shell_offset"] is not None:
                values["shell_offset"] = round(values["shell_offset"])
        elif implementation == "subtract 1":
            for path in values:
                values[path] -= 1
        elif implementation == "positive input stored as reciprocal":
            for path in values:
                if values[path] > 0:
                    values[path] = 1.0 / values[path]
        else:
            raise CommandBindingError(f"transform {implementation!r} is not executable")


def _scale_command_value(value: Any, factor: float) -> Any:
    from ..wire import Vec2, Vec3, WireVector

    if isinstance(value, WireVector):
        return replace(value, items=[_scale_command_value(item, factor) for item in value.items])
    if isinstance(value, Vec2):
        return Vec2(value.x * factor, value.y * factor)
    if isinstance(value, Vec3):
        return Vec3(value.x * factor, value.y * factor, value.z * factor)
    return value * factor


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
    blockers = removal_references(session, record_path)
    if blockers:
        raise ReferenceIntegrityError(record_path, blockers)
    session.snapshot()
    removed = parent.items.pop(key)
    warnings: List[str] = []
    tokens = _paths.tokenize(record_path)
    if len(tokens) == 2 and tokens[0] == "effect_descriptions":
        old_entries = session.working.effect_name_map.items
        removed_aliases = [entry for entry in old_entries if entry.target.value == key]
        adjusted_entries = []
        shifted = 0
        for entry in old_entries:
            target = entry.target.value
            if target == key:
                continue
            if target > key:
                entry = replace(entry, target=entry.target.replace(target - 1))
                shifted += 1
            adjusted_entries.append(entry)
        session.working.effect_name_map.items[:] = adjusted_entries
        if removed_aliases:
            warnings.append(f"removed {len(removed_aliases)} matching effect-name alias(es)")
        if shifted:
            warnings.append(f"shifted {shifted} effect-name target(s) after index {key}")
    change = session.record_change(record_path, before=removed, after=None, reason="user", warnings=warnings)
    return ChangeSet(changes=[change], diagnostics=[])


def removal_references(session: EditorSession, record_path: str) -> List[Reference]:
    """Known references that prevent a record from being removed safely."""

    tokens = _paths.tokenize(record_path)
    if len(tokens) != 2 or not isinstance(tokens[1], int):
        return []
    collection, index = tokens
    if collection == "effect_descriptions":
        names = {
            entry.name.decoded
            for entry in session.working.effect_name_map.items
            if entry.target.value == index and entry.name.decoded
        }
        references = [reference for name in names for reference in references_to_name(session.working, name)]
    elif collection == "effect_name_map":
        entries = session.working.effect_name_map.items
        if index >= len(entries) or not entries[index].name.decoded:
            return []
        references = references_to_name(session.working, entries[index].name.decoded)
    else:
        return []
    return list({reference.path: reference for reference in references}.values())


def add_effect(session: EditorSession, name: str) -> ChangeSet:
    """Allocates an EffectDescription and its effect-name lookup entry
    together (effdir-editor-spec.md, "Add an effect description"). The
    map target is the newly allocated description index, as established by
    the vanilla file's complete 0..N-1 target permutation."""

    session.snapshot()
    description = default_effect_description()
    session.working.effect_descriptions.items.append(description)
    effect_index = len(session.working.effect_descriptions.items) - 1

    from ..model.common import StringU32Pair
    from ..wire import make_raw_u32

    session.working.effect_name_map.items.append(
        StringU32Pair(name=WireString.from_text(name), target=make_raw_u32(effect_index))
    )

    change = session.record_change(
        f"effect_descriptions[{effect_index}]",
        before=None,
        after=description,
        reason="allocation",
        warnings=[],
    )
    return ChangeSet(changes=[change], diagnostics=[])


def validate(session: EditorSession) -> List[Diagnostic]:
    return validate_resource(session.working, dirty=session.dirty)


def opaque_ranges(session: EditorSession, encoded_length: int) -> List[Tuple[int, int]]:
    """Byte ranges of the encoded resource not backed by any decoded
    field -- see opaque_ranges.py for why this isn't a full coverage map."""

    return _opaque_ranges(session.working, encoded_length)


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
    diagnostics = validate(session)
    blocking = [d for d in diagnostics if d.severity == "error"]
    if blocking and not (not session.dirty and all(d.code == "unparsed_resource" for d in blocking)):
        raise ValidationError(blocking)
    backup_path = session.source.backup(session.handle)
    data = write_resource(session.working)
    result = session.source.write(session.handle, data, write_options)
    session.undo_stack.clear()
    session.redo_stack.clear()
    session.change_log.clear()
    return CommitResult(
        output_path=result.path,
        backup_path=backup_path,
        diagnostics=diagnostics,
        warnings=result.warnings,
    )


def undo(session: EditorSession) -> ChangeSet:
    session.undo()
    return ChangeSet(changes=[], diagnostics=[])


def redo(session: EditorSession) -> ChangeSet:
    session.redo()
    return ChangeSet(changes=[], diagnostics=[])
