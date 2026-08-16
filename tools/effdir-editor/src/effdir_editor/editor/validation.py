"""Semantic checks for an editable EFFDIR resource."""

from __future__ import annotations

import math
from dataclasses import fields, is_dataclass
from typing import Any, List

from ..model.common import ReadProfile
from ..model.resource import EffDirResource
from ..wire import Diagnostic, Raw, WireString, WireVector
from .references import COMPONENT_COLLECTIONS, NAME_BASED_COMPONENT_TYPES

_U32_SENTINEL = 0xFFFFFFFF
_TOP_LEVEL_MARKERS = {
    "marker_particles_decals": 1,
    "marker_decals_shakes": 0,
    "marker_shakes_lights": 0,
    "marker_components_dynamic": 1,
    "marker_dynamic_effects": 2,
    "marker_key_map_triggers": 0,
}
_COMPONENT_MARKERS = {
    "components.brushes": 0,
    "components.attractors": 0,
    "components.scrubbers": 1,
    "components.sequences": 1,
    "components.sounds": 0,
    "components.cameras": 0,
}


def _diagnostic(severity: str, code: str, message: str, path: str | None = None) -> Diagnostic:
    return Diagnostic(severity=severity, code=code, message=message, path=path)


def _walk_values(value: Any, path: str, diagnostics: List[Diagnostic]) -> None:
    if isinstance(value, Raw):
        if value.wire_type == "f32" and not math.isfinite(value.value):
            diagnostics.append(
                _diagnostic("error", "non_finite_float", "f32 value is not finite", path)
            )
        return
    if isinstance(value, WireString):
        if not value.valid:
            diagnostics.append(
                _diagnostic("warning", "invalid_string_encoding", "string is not valid UTF-8", path)
            )
        return
    if isinstance(value, WireVector):
        for index, item in enumerate(value.items):
            _walk_values(item, f"{path}[{index}]", diagnostics)
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            diagnostics.append(
                _diagnostic("error", "non_finite_float", "float value is not finite", path)
            )
        return
    if is_dataclass(value):
        for item in fields(value):
            if item.name == "preservation":
                continue
            child_path = f"{path}.{item.name}" if path else item.name
            _walk_values(getattr(value, item.name), child_path, diagnostics)


def _collection(resource: EffDirResource, path: str):
    value: Any = resource
    for token in path.split("."):
        value = getattr(value, token)
    return value


def validate_resource(resource: EffDirResource, *, dirty: bool = False) -> List[Diagnostic]:
    diagnostics = list(resource.preservation.diagnostics)
    _walk_values(resource, "", diagnostics)

    major = int(resource.version.major.value)
    minor = int(resource.version.minor.value)
    if major not in (3, 4):
        diagnostics.append(
            _diagnostic("error", "unsupported_major_version", f"unsupported major version {major}", "version.major")
        )
    expected_profile = ReadProfile.VERSION1 if minor == 1 else ReadProfile.CURRENT
    if resource.read_profile is not expected_profile:
        diagnostics.append(
            _diagnostic(
                "error",
                "version_profile_mismatch",
                f"version minor {minor} does not match read profile {resource.read_profile.value}",
                "version.minor",
            )
        )
    if resource.read_profile is ReadProfile.VERSION1 and dirty:
        diagnostics.append(
            _diagnostic(
                "error",
                "version1_edit_unsupported",
                "version-1 resources cannot be edited until a version-1 writer is confirmed",
                "version.minor",
            )
        )
    if major == 3 and resource.dynamic_particles.items:
        diagnostics.append(
            _diagnostic(
                "error",
                "major3_dynamic_particles",
                "major-3 resources cannot serialize dynamic particles",
                "dynamic_particles",
            )
        )

    for field_name, expected in _TOP_LEVEL_MARKERS.items():
        actual = int(getattr(resource, field_name).value)
        if actual != expected:
            diagnostics.append(
                _diagnostic(
                    "warning",
                    "unexpected_marker",
                    f"expected marker {expected}, found {actual}",
                    field_name,
                )
            )
    for collection_path, expected in _COMPONENT_MARKERS.items():
        collection = _collection(resource, collection_path)
        for index, record in enumerate(collection.items):
            if int(record.marker.value) != expected:
                diagnostics.append(
                    _diagnostic(
                        "warning",
                        "unexpected_marker",
                        f"expected marker {expected}, found {record.marker.value}",
                        f"{collection_path}[{index}].marker",
                    )
                )

    for index, entry in enumerate(resource.effect_name_map.items):
        target = int(entry.target.value)
        if not 0 <= target < len(resource.effect_descriptions.items):
            diagnostics.append(
                _diagnostic(
                    "error",
                    "dangling_effect_target",
                    f"effect-name target {target} is outside effect_descriptions",
                    f"effect_name_map[{index}].target",
                )
            )

    for effect_index, effect in enumerate(resource.effect_descriptions.items):
        effect_path = f"effect_descriptions[{effect_index}]"
        for description_index, description in enumerate(effect.descriptions.items):
            description_path = f"{effect_path}.descriptions[{description_index}]"
            component_type = int(description.component_type.value)
            component = COMPONENT_COLLECTIONS.get(component_type)
            target = int(description.description_index.value)
            if component is None:
                if component_type not in NAME_BASED_COMPONENT_TYPES:
                    diagnostics.append(
                        _diagnostic(
                            "warning",
                            "unknown_component_type",
                            f"component type {component_type} has no verified collection mapping",
                            f"{description_path}.component_type",
                        )
                    )
                continue
            if target == _U32_SENTINEL:
                diagnostics.append(
                    _diagnostic(
                        "warning",
                        "unresolved_component_target",
                        "component description target is unresolved",
                        f"{description_path}.description_index",
                    )
                )
                continue
            collection_path, _ = component
            collection = _collection(resource, collection_path)
            if not 0 <= target < len(collection.items):
                diagnostics.append(
                    _diagnostic(
                        "error",
                        "dangling_component_target",
                        f"component target {target} is outside {collection_path}",
                        f"{description_path}.description_index",
                    )
                )

        for event_index, event in enumerate(effect.events.items):
            event_path = f"{effect_path}.events[{event_index}].value"
            flags = int(event.flags.value)
            target = int(event.value.value)
            if flags & 1 and not 0 <= target < len(resource.shakes.items):
                diagnostics.append(
                    _diagnostic(
                        "error",
                        "dangling_shake_target",
                        f"shake target {target} is outside shakes",
                        event_path,
                    )
                )
            if flags & 0xC and not 0 <= target < len(resource.lights.items):
                diagnostics.append(
                    _diagnostic(
                        "error",
                        "dangling_light_target",
                        f"light target {target} is outside lights",
                        event_path,
                    )
                )

    metadata = resource.trailing_float_metadata
    if metadata.present.value != 0:
        if metadata.marker is None or metadata.count is None or metadata.values is None:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "incomplete_trailing_metadata",
                    "trailing float metadata is marked present but is incomplete",
                    "trailing_float_metadata",
                )
            )
        elif len(metadata.values) != metadata.count.value + 4:
            diagnostics.append(
                _diagnostic(
                    "error",
                    "invalid_trailing_float_count",
                    f"camera parameters have {len(metadata.values)} values; expected "
                    f"{metadata.count.value + 4} ({metadata.count.value} zoom levels plus four scalars)",
                    "trailing_float_metadata.values",
                )
            )
    elif any(value is not None for value in (metadata.marker, metadata.count, metadata.values)):
        diagnostics.append(
            _diagnostic(
                "warning",
                "unexpected_trailing_metadata",
                "trailing float metadata is marked absent but still has values",
                "trailing_float_metadata",
            )
        )
    return diagnostics
