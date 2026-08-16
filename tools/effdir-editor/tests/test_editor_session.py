import pytest

from effdir_editor.container.adapter import LocalFileEffDirSource, ResourceHandle
from effdir_editor.editor import api
from effdir_editor.editor.references import build_reference_index
from effdir_editor.editor.session import EditorSession
from effdir_editor.model.common import MessageTrigger
from effdir_editor.model.components import default_camera
from effdir_editor.model.particle import default_particle
from effdir_editor.model.resource import default_resource
from effdir_editor.wire import WireString, WireVector, make_raw_u32


def _session() -> EditorSession:
    return EditorSession(
        handle=ResourceHandle(package_path="", tgi=""),
        source=LocalFileEffDirSource(),
        original_bytes=b"",
        working=default_resource(),
    )


def test_undo_and_redo_restore_change_log_and_dirty_paths():
    session = _session()
    session.working.particles.items.append(default_particle())

    api.set_raw(session, "particles[0].preroll", 3.0)
    assert session.working.particles.items[0].preroll.value == 3.0
    assert [change.path for change in session.change_log] == ["particles[0].preroll"]
    assert session.dirty_paths == {"particles[0].preroll"}

    api.undo(session)
    assert session.working.particles.items[0].preroll.value == 0.0
    assert session.change_log == []
    assert session.dirty_paths == set()
    assert session.dirty is False

    api.redo(session)
    assert session.working.particles.items[0].preroll.value == 3.0
    assert [change.path for change in session.change_log] == ["particles[0].preroll"]
    assert session.dirty_paths == {"particles[0].preroll"}
    assert session.dirty is True


def test_new_edit_after_undo_discards_redo_state_and_old_change_log():
    session = _session()
    session.working.particles.items.append(default_particle())
    api.set_raw(session, "particles[0].preroll", 3.0)
    api.undo(session)

    api.set_raw(session, "particles[0].preroll", 4.0)
    assert session.redo_stack == []
    assert len(session.change_log) == 1
    assert session.change_log[0].before == 0.0
    assert session.change_log[0].after == 4.0


def test_add_effect_allocates_its_actual_description_index():
    session = _session()
    api.add_effect(session, "first")
    api.add_effect(session, "second")

    assert [entry.target.value for entry in session.working.effect_name_map.items] == [0, 1]
    assert [effect.chain_effect.decoded for effect in session.working.effect_descriptions.items] == ["", ""]
    assert session.new_paths == {"effect_descriptions[0]", "effect_descriptions[1]"}

    api.undo(session)
    assert session.new_paths == {"effect_descriptions[0]"}

    api.redo(session)
    assert session.new_paths == {"effect_descriptions[0]", "effect_descriptions[1]"}


def test_effect_removal_blocks_external_references_then_cascades_alias_indices():
    session = _session()
    api.add_effect(session, "first")
    api.add_effect(session, "second")
    session.working.message_triggers.items.append(
        MessageTrigger(message_id=make_raw_u32(0x12345678), effect_name=WireString.from_text("first"))
    )

    with pytest.raises(api.ReferenceIntegrityError) as exc_info:
        api.remove_record(session, "effect_descriptions[0]")
    assert [reference.path for reference in exc_info.value.references] == ["message_triggers[0]"]
    assert len(session.working.effect_descriptions.items) == 2

    session.working.message_triggers.items.clear()
    change_set = api.remove_record(session, "effect_descriptions[0]")

    assert len(session.working.effect_descriptions.items) == 1
    assert [entry.name.decoded for entry in session.working.effect_name_map.items] == ["second"]
    assert [entry.target.value for entry in session.working.effect_name_map.items] == [0]
    assert "removed 1 matching effect-name alias(es)" in change_set.changes[0].warnings
    assert "shifted 1 effect-name target(s) after index 0" in change_set.changes[0].warnings


def test_set_command_requires_confirmation_for_parser_evidence():
    session = _session()
    session.working.particles.items.append(default_particle())

    with pytest.raises(api.EvidenceConfirmationRequired):
        api.set_command(session, "particles[0].preroll", 2.5)

    assert session.dirty is False
    assert session.working.particles.items[0].preroll.value == 0.0


def test_set_rate_command_writes_curve_without_inject_presence_bit():
    session = _session()
    session.working.particles.items.append(default_particle())
    curve = WireVector(count=2, items=[2.0, 4.0], source_span=None)

    changes = api.set_command(session, "particles[0].emit", curve, confirm_parser=True)

    particle = session.working.particles.items[0]
    assert particle.emit_curve == curve
    assert not particle.flags_0.value & (1 << 1)
    assert {change.path for change in changes.changes} == {"particles[0].emit_curve"}
    assert len(session.undo_stack) == 1

    api.undo(session)
    particle = session.working.particles.items[0]
    assert particle.emit_curve.items == [30.0]
    assert particle.flags_0.value == 0


def test_set_command_detects_and_can_resolve_presence_bit_conflicts():
    session = _session()
    session.working.particles.items.append(default_particle())
    curve = WireVector(count=1, items=[3.0], source_span=None)
    api.set_command(session, "particles[0].inject", curve, confirm_parser=True)

    with pytest.raises(api.CommandConflictError):
        api.set_command(session, "particles[0].maintain", curve, confirm_parser=True)

    api.set_command(
        session,
        "particles[0].maintain",
        curve,
        confirm_parser=True,
        resolve_conflicts=True,
    )
    flags = session.working.particles.items[0].flags_0.value
    assert not flags & (1 << 1)
    assert flags & (1 << 2)


def test_get_node_uses_supplied_reference_index(monkeypatch):
    session = _session()
    reference_index = build_reference_index(session.working)

    def unexpected_rebuild(_resource):
        raise AssertionError("reference index was rebuilt")

    monkeypatch.setattr(api, "build_reference_index", unexpected_rebuild)
    node = api.get_node(session, "effect_descriptions", reference_index=reference_index)

    assert node.summary.path == "effect_descriptions"


def test_set_command_applies_runtime_transform_without_confirmation():
    session = _session()
    session.working.components.cameras.items.append(default_camera())

    api.set_command(session, "components.cameras[0].zoom", 4)

    camera = session.working.components.cameras.items[0]
    assert camera.zoom.value == 3
    assert camera.flags.value & 1
