"""Curve presentation helpers for the editor UI.

The wire model keeps curves as ordinary vectors. This module only identifies
vectors that have an evidence-backed curve binding. It does not change the
wire representation or claim a runtime interpolation rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..wire import WireVector
from .nodes import Node

_NON_SCALAR_CURVES = {
    ("ParticleDescriptor", "wiggles"),
    ("ParticleDescriptor", "color_curve"),
    ("DecalDescriptor", "color"),
    ("LightDescriptor", "color"),
}

# These vectors are scalar sample curves in the recovered model, even where
# the command catalog does not yet contain a complete command entry. Keep the
# list explicit so ordinary numeric vectors such as model-key lists do not
# open the curve editor by accident.
_SCALAR_CURVE_FIELDS = {
    "emit_curve",
    "alpha_curve",
    "size_curve",
    "aspect_curve",
    "rotate_curve",
    "alpha_warp_curve",
    "attractor_curve",
    "explosion_curve",
    "rotation",
    "size",
    "alpha",
    "aspect",
    "amplitude",
    "frequency",
    "strength",
}


@dataclass(frozen=True)
class CurveInfo:
    path: str
    commands: tuple[str, ...]


def curve_info(node: Node) -> Optional[CurveInfo]:
    """Return curve display data for a scalar curve vector, if supported."""

    if not isinstance(node.value, WireVector):
        return None
    bindings = [binding for binding in node.bindings if binding.encoding == "curve"]
    field_name = node.summary.path.rsplit(".", 1)[-1]
    if not bindings and field_name not in _SCALAR_CURVE_FIELDS:
        return None
    if any(
        (binding.record_type, member_path) in _NON_SCALAR_CURVES
        for binding in bindings
        for member_path in binding.member_paths
    ):
        return None
    # Color curves and record vectors need a channel-aware editor. Keep them
    # in the normal vector editor until that view has an exact edit contract.
    if any(not isinstance(item, (int, float)) for item in node.value.items):
        return None
    commands = tuple(dict.fromkeys(binding.command_path for binding in bindings))
    if not commands:
        commands = (field_name.removesuffix("_curve"),)
    return CurveInfo(path=node.summary.path, commands=commands)
