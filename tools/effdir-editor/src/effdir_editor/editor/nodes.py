"""NodeSummary/Node construction (effdir-editor-spec.md, "Core/editor API")
via reflection over the resource model dataclasses, plus the command
binding catalog for labels/evidence. No wx dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, List, Optional, Set, Tuple

from ..bindings.catalog import CommandBinding, find_bindings
from ..wire import Bounds2, Bounds3, Raw, Vec2, Vec3, WireString, WireVector
from .paths import format_tokens, get_path, parent_path, tokenize
from .references import Reference, ReferenceIndex

VALUE_TYPES = (Vec2, Vec3, Bounds2, Bounds3)

_HIDDEN_FIELDS = {"preservation"}

# Record types that carry their own display-worthy name directly on a
# field, keyed to which attribute holds it -- used to give the resource
# tree a meaningful label instead of a bare "[i]" index.
_SELF_NAME_FIELD = {
    "StringU32Pair": "name",  # effect_name_map entries
    "StringU32U32Record": "name",  # effect_key_map entries
    "MessageTrigger": "effect_name",
    "SequenceItem": "effect_name",  # empty for a "wait" item, a name for "play"
}


def _self_display_name(value: Any) -> Optional[str]:
    if not is_dataclass(value):
        return None
    field_name = _SELF_NAME_FIELD.get(type(value).__name__)
    if field_name is None:
        return None
    name_field = getattr(value, field_name, None)
    return name_field.decoded if isinstance(name_field, WireString) and name_field.decoded else None


def resolve_display_name(value: Any, path: str, reference_index: Optional[ReferenceIndex]) -> Optional[str]:
    """Display-worthy name for `value` at `path`: either a name it carries
    directly (`_SELF_NAME_FIELD`), or -- for an `EffectDescription`, whose
    own `effect_name` reads back empty in real files -- the name resolved
    through `effect_name_map` (see references.py's docstring). Takes an
    already-known `value`/`path` pair rather than re-deriving them from
    `root`, so callers walking many nodes (search.py) can call this without
    repeating a root-to-node traversal per node."""

    name = _self_display_name(value)
    if name is not None:
        return name
    if reference_index and is_dataclass(value) and type(value).__name__ == "EffectDescription":
        tokens = tokenize(path)
        if len(tokens) >= 2 and tokens[-2] == "effect_descriptions" and isinstance(tokens[-1], int):
            return reference_index.names.get(tokens[-1])
    return None


def resolve_record_type(kind: str, value: Any) -> str:
    if kind == "scalar":
        if isinstance(value, Raw):
            return value.wire_type
        return "f32" if isinstance(value, float) else "u32"
    if kind == "string":
        return "string"
    if kind == "value" or is_dataclass(value) or isinstance(value, WireVector):
        return type(value).__name__
    return kind


@dataclass(frozen=True)
class RawValue:
    path: str
    wire_type: str
    value: Any
    raw_bytes: bytes


@dataclass(frozen=True)
class NodeSummary:
    path: str
    record_type: str
    label: Optional[str]
    evidence: str
    dirty: bool
    reference_count: int = 0
    display_name: Optional[str] = None


@dataclass(frozen=True)
class Node:
    summary: NodeSummary
    value: Any
    raw: Optional[RawValue]
    bindings: List[CommandBinding]
    referenced_by: List[Reference] = field(default_factory=list)


def classify(value: Any) -> str:
    if isinstance(value, WireVector):
        return "collection"
    if isinstance(value, Raw):
        return "scalar"
    if isinstance(value, WireString):
        return "string"
    if isinstance(value, VALUE_TYPES):
        return "value"
    if is_dataclass(value):
        return "record"
    # Vector elements are plain, unwrapped values (only top-level scalar
    # members get a Raw[T] wrapper -- see wire/types.py's module docstring
    # and effdir-editor-spec.md's vector<T> grammar examples).
    if isinstance(value, bool):
        return "opaque"
    if isinstance(value, (int, float)):
        return "scalar"
    if isinstance(value, str):
        return "string"
    return "opaque"


def _join(path: str, child: str) -> str:
    return f"{path}.{child}" if path else child


def child_paths(root: Any, path: str) -> List[str]:
    value = get_path(root, path) if path else root
    kind = classify(value)
    if kind == "collection":
        return [f"{path}[{i}]" if path else f"[{i}]" for i in range(len(value.items))]
    if kind in ("record", "value"):
        return [_join(path, f.name) for f in fields(value) if f.name not in _HIDDEN_FIELDS]
    return []


def iter_child_values(value: Any) -> List[Tuple[str, Any]]:
    """Like `child_paths`, but works from an already-resolved `value` and
    returns `(path_suffix, child_value)` pairs instead of full path
    strings. For a full recursive walk (search.py), this avoids
    `child_paths`/`build_node`'s per-call root-to-node re-traversal, which
    turns O(n) into O(n^2) over a large resource."""

    kind = classify(value)
    if kind == "collection":
        return [(f"[{i}]", item) for i, item in enumerate(value.items)]
    if kind in ("record", "value"):
        return [(f.name, getattr(value, f.name)) for f in fields(value) if f.name not in _HIDDEN_FIELDS]
    return []


def _parent_record_type(root: Any, path: str) -> Optional[str]:
    tokens = tokenize(path)
    if len(tokens) < 2:
        return None
    parent = get_path(root, parent_path(path))
    return type(parent).__name__ if is_dataclass(parent) else None


def build_node(
    root: Any,
    path: str,
    *,
    dirty_paths: Set[str] = frozenset(),
    reference_index: Optional[ReferenceIndex] = None,
) -> Node:
    value = get_path(root, path) if path else root
    kind = classify(value)
    tokens = tokenize(path)
    attr_name = tokens[-1] if tokens else None

    display_name = resolve_display_name(value, path, reference_index)
    referenced_by: List[Reference] = []
    if (
        reference_index
        and is_dataclass(value)
        and type(value).__name__ == "EffectDescription"
        and len(tokens) >= 2
        and tokens[-2] == "effect_descriptions"
        and isinstance(tokens[-1], int)
    ):
        referenced_by = reference_index.backlinks.get(tokens[-1], [])

    bindings: List[CommandBinding] = []
    if isinstance(attr_name, str):
        parent_type = _parent_record_type(root, path)
        if parent_type:
            bindings = find_bindings(parent_type, attr_name)

    raw_value: Optional[RawValue] = None
    plain_value: Any = value
    if kind == "scalar":
        if isinstance(value, Raw):
            raw_value = RawValue(path=path, wire_type=value.wire_type, value=value.value, raw_bytes=value.raw_bytes)
            plain_value = value.value
        else:
            # Unwrapped vector element (plain float/int); infer a wire
            # type label since there's no Raw wrapper to read it from.
            wire_type = "f32" if isinstance(value, float) else "u32"
            raw_value = RawValue(path=path, wire_type=wire_type, value=value, raw_bytes=b"")
            plain_value = value
    elif kind == "string":
        if isinstance(value, WireString):
            raw_value = RawValue(path=path, wire_type="string", value=value.decoded, raw_bytes=value.raw_bytes)
            plain_value = value.decoded
        else:
            raw_value = RawValue(path=path, wire_type="string", value=value, raw_bytes=b"")
            plain_value = value

    record_type = resolve_record_type(kind, value)
    summary = NodeSummary(
        path=path,
        record_type=record_type,
        label=bindings[0].command_path if bindings else None,
        evidence=bindings[0].evidence if bindings else "wire",
        dirty=path in dirty_paths,
        reference_count=len(referenced_by),
        display_name=display_name,
    )
    return Node(summary=summary, value=plain_value, raw=raw_value, bindings=bindings, referenced_by=referenced_by)
