"""EFFDIR `EffectDescription` -> fx `effect NAME [switches] ... end`.

Top-level switches map from `docs/reference/top-level/effect.md`'s
9-bit flag word (effdir.md, "Effect records" flag table). Children
dispatch by `DescriptionRecord.component_type` through
`editor/references.py`'s `COMPONENT_COLLECTIONS` table -- the same
table the editor's own reference navigation already trusts. Events
dispatch by `EventRecord.flags` bits 0/2/3 (effdir.md, "Event bit"
table) into `shakeEffect`/`flashEffect`/`tintEffect`
(docs/reference/effect-children/{shake,flash,tint}-effect.md).
"""

from __future__ import annotations

import math
from typing import List

from ..editor.references import COMPONENT_COLLECTIONS
from ..model.common import ReadProfile
from ..model.effect import DescriptionRecord, EffectDescription
from ..model.resource import EffDirResource
from .bits import bit
from .coverage import Coverage
from .defaults import EFFECT_DEFAULT, UNINITIALIZED_U32
from .inline_components import automata_effect_lines, brush_effect_lines, camera_effect_lines, scrubber_effect_lines, sound_effect_lines
from .names import ResolvedNames
from .writer import FxWriter, fmt_hex, fmt_num, fmt_vec3, quote_name

_TOP_LEVEL_FLAG_SWITCHES = [
    (0, "viewRelative"),
    (1, "noAutoStop"),
    (2, "hardStop"),
    (3, "rigid"),
    (4, "noPropagate"),
    (5, "applyCursor"),
    (6, "ignoreOrientation"),
    (7, "noLODStop"),
    (8, "manualRestart"),
]

_IDENTITY_ROWS = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _collection_len(resource: EffDirResource, collection_path: str) -> int:
    target = resource
    for token in collection_path.split("."):
        target = getattr(target, token)
    return len(target.items)


def _matrix_is_identity(matrix) -> bool:
    rows = ((matrix.row_0.x, matrix.row_0.y, matrix.row_0.z), (matrix.row_1.x, matrix.row_1.y, matrix.row_1.z), (matrix.row_2.x, matrix.row_2.y, matrix.row_2.z))
    return rows == _IDENTITY_ROWS


def _matrix_to_xyz_degrees(matrix):
    """Invert the parser's ``Rx(x) * Ry(y) * Rz(z)`` construction.

    Euler angles are not unique, so choose the conventional branch with
    Y in [-90, 90] and Z=0 at gimbal lock.  Rebuilding the matrix keeps us
    from emitting a rotation for matrices that did not come from this
    parser path (scale/shear/non-finite values).
    """

    rows = (
        (matrix.row_0.x, matrix.row_0.y, matrix.row_0.z),
        (matrix.row_1.x, matrix.row_1.y, matrix.row_1.z),
        (matrix.row_2.x, matrix.row_2.y, matrix.row_2.z),
    )
    if not all(math.isfinite(value) for row in rows for value in row):
        return None

    sy = max(-1.0, min(1.0, rows[0][2]))
    y = math.asin(sy)
    cy = math.cos(y)
    if abs(cy) > 1e-6:
        x = math.atan2(-rows[1][2], rows[2][2])
        z = math.atan2(-rows[0][1], rows[0][0])
    elif sy >= 0.0:
        z = 0.0
        x = math.atan2(rows[1][0], rows[1][1])
    else:
        z = 0.0
        x = math.atan2(-rows[1][0], rows[1][1])

    sx, cx = math.sin(x), math.cos(x)
    sy, cy = math.sin(y), math.cos(y)
    sz, cz = math.sin(z), math.cos(z)
    rebuilt = (
        (cy * cz, -cy * sz, sy),
        (sx * sy * cz + cx * sz, -sx * sy * sz + cx * cz, -sx * cy),
        (-cx * sy * cz + sx * sz, cx * sy * sz + sx * cz, cx * cy),
    )
    if any(abs(actual - expected) > 1e-4 for row, expected_row in zip(rows, rebuilt) for actual, expected in zip(row, expected_row)):
        return None
    return tuple(math.degrees(angle) for angle in (x, y, z))


def _shared_child_options(
    d: DescriptionRecord,
    *,
    allow_shells: bool,
    in_select: bool,
    coverage: Coverage,
    path: str,
) -> List[str]:
    opts: List[str] = []
    t = d.legacy_transform

    if t.translation.x != 0.0 or t.translation.y != 0.0 or t.translation.z != 0.0:
        opts.append(f"-offset {fmt_vec3(t.translation)}")
    if t.scale != 1.0:
        opts.append(f"-scale {fmt_num(t.scale)}")
    if not _matrix_is_identity(t.matrix):
        angles = _matrix_to_xyz_degrees(t.matrix)
        if angles is None:
            coverage.note(
                f"{path}.legacy_transform.matrix",
                "unsupported",
                "non-identity matrix is not a finite parser-style rotation matrix; omitted",
            )
        else:
            opts.append("-rotateXYZ " + " ".join(fmt_num(angle) for angle in angles))

    lod = int(d.lod.value)
    lod_range = int(d.lod_range.value)
    if (lod, lod_range) != (1, 6):
        if lod_range == lod + 1:
            opts.append(f"-lod {lod}")
        elif lod_range >= 1:
            opts.append(f"-lodRange {lod} {lod_range - 1}")
        else:
            coverage.note(
                f"{path}.lod_range",
                "unsupported",
                "stored LOD upper-bound byte is zero, which cannot be inverted as parser max + 1",
            )
    if allow_shells and (d.shell_count.value != 1 or d.shell_offset.value != 16):
        opts.append(f"-shells {int(d.shell_count.value)} {int(d.shell_offset.value)}")
    if d.emit_scale_min.value != 1.0 or d.emit_scale_max.value != 1.0:
        opts.append(f"-emitScale {fmt_num(d.emit_scale_min.value)} {fmt_num(d.emit_scale_max.value)}")
    if d.size_scale_min.value != 1.0 or d.size_scale_max.value != 1.0:
        opts.append(f"-sizeScale {fmt_num(d.size_scale_min.value)} {fmt_num(d.size_scale_max.value)}")
    if bit(d.flags.value, 0):
        opts.append("-ignoreLength")
    if d.probability.value != 0:
        if in_select:
            opts.append(f"-prob {fmt_num(d.probability.value / 65535.0)}")
        else:
            coverage.note(
                f"{path}.probability",
                "unsupported",
                f"stored probability {int(d.probability.value)} is only legal inside a select block",
            )
    return opts


def _emit_description_record(
    writer: FxWriter,
    coverage: Coverage,
    resource: EffDirResource,
    names: ResolvedNames,
    effect_index: int,
    description_index: int,
    d: DescriptionRecord,
    *,
    in_select: bool,
) -> None:
    path = f"effect_descriptions[{effect_index}].descriptions[{description_index}]"
    component_type = d.component_type.value

    if component_type == 2:
        shared = _shared_child_options(d, allow_shells=False, in_select=in_select, coverage=coverage, path=path)
        writer.line(f"visualEffect {quote_name(d.name.decoded or '')}" + "".join(f" {o}" for o in shared))
        coverage.emitted()
        return
    collection = COMPONENT_COLLECTIONS.get(component_type)
    if collection is None:
        coverage.skipped(path, f"component_type {component_type} is not in the confirmed component-type table")
        return
    collection_path, _label = collection
    index = d.description_index.value
    if not (0 <= index < _collection_len(resource, collection_path)):
        coverage.skipped(path, f"description_index {index} is out of range for {collection_path}")
        return

    name = names.name_for(component_type, index)
    shared = _shared_child_options(
        d,
        allow_shells=(component_type == 0),
        in_select=in_select,
        coverage=coverage,
        path=path,
    )

    if component_type == 0:
        writer.line(f"particleEffect {quote_name(name)}" + "".join(f" {o}" for o in shared))
        coverage.emitted()
    elif component_type == 1:
        writer.line(f"decalEffect {quote_name(name)}" + "".join(f" {o}" for o in shared))
        coverage.emitted()
    elif component_type == 16:
        writer.line(f"dynamicParticleEffect {quote_name(name)}" + "".join(f" {o}" for o in shared))
        coverage.emitted()
    elif component_type == 6:
        writer.line(f"sequence {quote_name(name)}" + "".join(f" {o}" for o in shared))
        coverage.emitted()
    elif component_type == 3:
        record = resource.components.brushes.items[index]
        # The ID map resolves only name -> resource key. Every invocation
        # constructs a fresh description, so all options must be repeated.
        writer.multiline_command(brush_effect_lines(name, record, coverage=coverage, path=path) + shared)
        coverage.emitted()
    elif component_type == 4:
        record = resource.components.attractors.items[index]
        writer.multiline_command(automata_effect_lines(record.name.decoded or name, record, coverage=coverage, path=path) + shared)
        coverage.emitted()
    elif component_type == 5:
        record = resource.components.scrubbers.items[index]
        lines = scrubber_effect_lines(record, coverage=coverage, path=path)
        if lines:
            writer.multiline_command(lines + shared)
            coverage.emitted()
        else:
            # Dropping the command outright would also drop this child's
            # transform, silently changing the effect's shape. Keep the
            # child (scrubber_effect_lines already recorded why it has no
            # options) so the placement survives the round trip.
            writer.multiline_command(["scrubberEffect"] + shared)
            coverage.skipped(path, "scrubberEffect has no recoverable options; emitted as a bare command so its transform is not lost")
    elif component_type == 7:
        record = resource.components.sounds.items[index]
        writer.multiline_command(sound_effect_lines(name, record, coverage=coverage, path=path) + shared)
        coverage.emitted()
    elif component_type == 8:
        record = resource.components.cameras.items[index]
        lines = camera_effect_lines(record, coverage=coverage, path=path)
        if lines:
            writer.multiline_command(lines + shared)
            coverage.emitted()
        else:
            writer.multiline_command(["cameraEffect"] + shared)
            coverage.skipped(path, "cameraEffect had no nonzero fields; emitted as a bare command so its transform is not lost")


def _emit_child_range(
    writer: FxWriter,
    coverage: Coverage,
    resource: EffDirResource,
    names: ResolvedNames,
    effect_index: int,
    items,
    start: int,
    stop: int,
) -> None:
    i = start
    while i < stop:
        group = items[i].selection_group.value
        if group != 0:
            j = i
            while j < stop and items[j].selection_group.value == group:
                j += 1
            writer.begin("select")
            for k in range(i, j):
                _emit_description_record(writer, coverage, resource, names, effect_index, k, items[k], in_select=True)
            writer.end()
            i = j
        else:
            _emit_description_record(writer, coverage, resource, names, effect_index, i, items[i], in_select=False)
            i += 1


def _emit_children(writer: FxWriter, coverage: Coverage, resource: EffDirResource, names: ResolvedNames, effect_index: int, effect: EffectDescription) -> None:
    items = effect.descriptions.items
    i, n = 0, len(items)
    while i < n:
        is_system_sequence = bit(items[i].flags.value, 1)
        j = i + 1
        while j < n and bit(items[j].flags.value, 1) == is_system_sequence:
            j += 1
        if is_system_sequence:
            writer.begin("systemSequence")
        _emit_child_range(writer, coverage, resource, names, effect_index, items, i, j)
        if is_system_sequence:
            writer.end()
        i = j


def _emit_events(writer: FxWriter, coverage: Coverage, resource: EffDirResource, effect_index: int, effect: EffectDescription) -> None:
    for event_index, e in enumerate(effect.events.items):
        path = f"effect_descriptions[{effect_index}].events[{event_index}]"
        flags = e.flags.value
        index = e.value.value
        name = quote_name(e.name.decoded or "")
        matched = False

        if bit(flags, 0):
            matched = True
            if 0 <= index < len(resource.shakes.items):
                line = f"shakeEffect {name}"
                if not bit(flags, 1):
                    line += " -noEpicentre"
                writer.line(line)
                coverage.emitted()
            else:
                coverage.skipped(path, f"shake index {index} out of range")
        if bit(flags, 2):
            matched = True
            if 0 <= index < len(resource.lights.items):
                line = f"flashEffect {name}"
                if bit(flags, 1):
                    line += f" -epicentre {fmt_num(e.time.value)}"
                writer.line(line)
                coverage.emitted()
            else:
                coverage.skipped(path, f"light index {index} out of range")
        if bit(flags, 3):
            matched = True
            if 0 <= index < len(resource.lights.items):
                writer.line(f"tintEffect {name}")
                coverage.emitted()
            else:
                coverage.skipped(path, f"light index {index} out of range")
        if not matched:
            coverage.skipped(path, f"event flags={flags} do not match any confirmed dispatch bit (0=shake, 2=flash, 3=tint)")


def emit_effect(
    writer: FxWriter,
    coverage: Coverage,
    resource: EffDirResource,
    names: ResolvedNames,
    effect_index: int,
    effect: EffectDescription,
    primary_name: str,
) -> None:
    switches: List[str] = []
    flags = effect.flags.value
    for bit_n, keyword in _TOP_LEVEL_FLAG_SWITCHES:
        if bit(flags, bit_n):
            switches.append(keyword)
    if effect.priority.value != EFFECT_DEFAULT.priority.value:
        if 1 <= effect.priority.value <= 5:
            switches.append(f"-priority {int(effect.priority.value)}")
        else:
            coverage.note(
                f"effect_descriptions[{effect_index}].priority",
                "unsupported",
                f"priority {int(effect.priority.value)} is outside the parser's accepted range 1..5",
            )
    if resource.read_profile != ReadProfile.VERSION1:
        messages = [effect.start_message_1.value, effect.start_message_2.value, effect.start_message_3.value]
        # The parser accepts one to three arguments and leaves unsupplied
        # trailing words untouched. Trim only the known Windows debug-fill
        # sentinel; an interior sentinel may have been explicitly authored.
        while len(messages) > 1 and messages[-1] == UNINITIALIZED_U32:
            messages.pop()
        if messages != [EFFECT_DEFAULT.start_message_1.value]:
            # Runtime passes word 1 to cRZMessage2::SetType, while words
            # 2/3 are SetData1/SetData2 payloads. SC4 message type IDs are
            # conventionally hexadecimal; payloads remain ordinary integers.
            switches.append(
                "-startMessage "
                + " ".join([fmt_hex(messages[0]), *(str(int(value)) for value in messages[1:])])
            )

    header = f"effect {quote_name(primary_name)}" + "".join(f" {s}" for s in switches)
    writer.begin(header)
    _emit_children(writer, coverage, resource, names, effect_index, effect)
    _emit_events(writer, coverage, resource, effect_index, effect)
    chain = effect.chain_effect.decoded or ""
    if chain:
        writer.line(f"chainEffect {quote_name(chain)}")
    writer.end()
    coverage.emitted()


def emit_effect_alias(writer: FxWriter, primary_name: str, alias_name: str) -> None:
    """A second `effect_name_map` entry pointing at the same
    `EffectDescription` has no direct fx spelling (one `effect` block
    defines exactly one name); a thin wrapper effect that plays the
    original is the closest equivalent."""

    writer.begin(f"effect {quote_name(alias_name)}")
    writer.line(f"visualEffect {quote_name(primary_name)}")
    writer.end()
