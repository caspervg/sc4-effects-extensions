"""NodeSummary/Node construction (effdir-editor-spec.md, "Core/editor API")
via reflection over the resource model dataclasses, plus the command
binding catalog for labels/evidence. No wx dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any, List, Optional, Set

from ..bindings.catalog import CommandBinding, find_bindings
from ..wire import Bounds2, Bounds3, Raw, Vec2, Vec3, WireString, WireVector
from .paths import format_tokens, get_path, parent_path, tokenize

VALUE_TYPES = (Vec2, Vec3, Bounds2, Bounds3)

_HIDDEN_FIELDS = {"preservation"}


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


@dataclass(frozen=True)
class Node:
    summary: NodeSummary
    value: Any
    raw: Optional[RawValue]
    bindings: List[CommandBinding]


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


def _parent_record_type(root: Any, path: str) -> Optional[str]:
    tokens = tokenize(path)
    if len(tokens) < 2:
        return None
    parent = get_path(root, parent_path(path))
    return type(parent).__name__ if is_dataclass(parent) else None


def build_node(root: Any, path: str, *, dirty_paths: Set[str] = frozenset()) -> Node:
    value = get_path(root, path) if path else root
    kind = classify(value)
    tokens = tokenize(path)
    attr_name = tokens[-1] if tokens else None

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

    if kind == "scalar":
        record_type = raw_value.wire_type
    elif kind == "string":
        record_type = "string"
    elif kind == "value" or is_dataclass(value) or isinstance(value, WireVector):
        record_type = type(value).__name__
    else:
        record_type = kind
    summary = NodeSummary(
        path=path,
        record_type=record_type,
        label=bindings[0].command_path if bindings else None,
        evidence=bindings[0].evidence if bindings else "wire",
        dirty=path in dirty_paths,
    )
    return Node(summary=summary, value=plain_value, raw=raw_value, bindings=bindings)
