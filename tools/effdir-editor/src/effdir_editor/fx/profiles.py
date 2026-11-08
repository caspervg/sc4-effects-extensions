"""Named compiler profiles.

The default profile is the game's own parser. Other profiles model a tool
that wrote `EFFDIR` files in a different way, so those files can be
reproduced without changing what the default produces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

# The zooms and scalars of a default-constructed `cSC4CameraParams` as written
# by the legacy tool: five zooms, parallax base and range, size, side swipe.
LEGACY_CAMERA_VALUES: Tuple[float, ...] = (2500.0, 1250.0, 625.0, 312.0, 156.0, 0.0, 0.0, 4.0, 7.0)


@dataclass(frozen=True)
class CompilerProfile:
    name: str
    # Effect name map stored in effect order instead of hash table order.
    target_ordered_names: bool = False
    # Written as the camera-present byte for default camera parameters.
    default_camera_fill: Optional[int] = None
    # The parsers normalize direction vectors before storing them.
    normalize_vectors: bool = True
    # Reject `-vary` and similar values outside their documented range.
    check_ranges: bool = True
    # Reject `-lod` and `-lodRange` inside a `select`.
    check_select_lod: bool = True
    # Allow `visualEffect` to name an effect defined in another resource.
    allow_external_effects: bool = False
    # A repeated pool name appends a record instead of replacing the earlier
    # one, and the k-th reference to a name uses its k-th definition.
    append_named_pools: bool = False
    # `-dir` adds and subtracts the parsed values before rounding the result.
    unrounded_direction_bounds: bool = False
    # Replay the game's transform `revision` counter on redefinition.
    track_revision: bool = True
    # Accept `-prob` on a child outside a `select`.
    allow_prob_outside_select: bool = False


GAME = CompilerProfile("game")

# ponytail: inferred from NAM and JENX output, the tool itself is unidentified.
LEGACY_TOOL = CompilerProfile(
    "legacy-tool",
    target_ordered_names=True,
    default_camera_fill=0xCD,
    normalize_vectors=False,
    check_ranges=False,
    check_select_lod=False,
    allow_external_effects=True,
    append_named_pools=True,
    unrounded_direction_bounds=True,
    track_revision=False,
    allow_prob_outside_select=True,
)

PROFILES: Dict[str, CompilerProfile] = {profile.name: profile for profile in (GAME, LEGACY_TOOL)}
