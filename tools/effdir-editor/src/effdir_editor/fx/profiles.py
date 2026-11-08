"""Named compiler profiles.

The default profile is the game's own parser. Other profiles model a tool
that wrote `EFFDIR` files in a different way, so those files can be
reproduced without changing what the default produces.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    # one, and the k-th reference to a name uses its k-th definition. Xannepan's
    # IsolateEff.m copies a new record for each child with no merging, and every
    # repeated pool name is in a file that kept vanilla's camera block.
    append_named_pools: bool = False
    # `-dir` adds and subtracts the parsed values before rounding the result.
    unrounded_direction_bounds: bool = False
    # Replay the game's transform `revision` counter on redefinition.
    track_revision: bool = True
    # Accept `-prob` on a child outside a `select`.
    allow_prob_outside_select: bool = False
    # Apply `matlab_scrubber_header` to every scrubber record.
    repeat_scrubber_header: bool = False


def matlab_scrubber_header(record: bytes) -> bytes:
    """A scrubber record as ReadEffDir.m and WriteEffDir.m (2012) leave it.

    Both scripts cover the first 22 bytes with three `ubit58` fields named
    `u1a, u1b, u1b`, so the third read replaces the second and the writer
    stores it twice. `fread` returns doubles, which keep 53 significant bits,
    and the two bits after the third field are not read.
    """

    value = int.from_bytes(record[:22], "little")
    mask = (1 << 58) - 1
    first = int(float(value & mask))
    third = int(float((value >> 116) & mask))
    return (first | third << 58 | third << 116).to_bytes(22, "little") + record[22:]


GAME = CompilerProfile("game")

# ponytail: inferred from NAM and JENX output. The `0xCD` lineage's tool is
# unidentified, the published Matlab scripts only copy that byte from their input.
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

# Xannepan's Matlab scripts from SC4Devotion topic 14724 (Nov 2012), for a file
# that went through this version of WriteEffDir.m. Not part of `legacy-tool`
# because six of the seven scrubbers in the JENX release do not show the damage.
MATLAB_2012 = replace(LEGACY_TOOL, name="matlab-2012", repeat_scrubber_header=True)

PROFILES: Dict[str, CompilerProfile] = {profile.name: profile for profile in (GAME, LEGACY_TOOL, MATLAB_2012)}
