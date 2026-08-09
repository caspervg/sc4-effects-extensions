from effdir_editor.editor.validation import validate_resource
from effdir_editor.editor import api
from effdir_editor.container.adapter import LocalFileEffDirSource, ResourceHandle
from effdir_editor.editor.session import EditorSession
from effdir_editor.model.common import StringU32Pair
from effdir_editor.model.effect import default_description_record, default_effect_description, default_event_record
from effdir_editor.model.resource import default_resource
from effdir_editor.wire import WireString, make_raw_bitset, make_raw_u32


def test_default_resource_has_no_semantic_errors():
    assert [d for d in validate_resource(default_resource()) if d.severity == "error"] == []


def test_invalid_effect_name_target_is_reported():
    resource = default_resource()
    resource.effect_name_map.items.append(
        StringU32Pair(name=WireString.from_text("broken"), target=make_raw_u32(4))
    )

    diagnostics = validate_resource(resource)

    assert [(d.code, d.path) for d in diagnostics] == [
        ("dangling_effect_target", "effect_name_map[0].target")
    ]


def test_invalid_component_and_event_targets_are_reported():
    resource = default_resource()
    effect = default_effect_description()
    description = default_description_record()
    description.description_index = make_raw_u32(3)
    effect.descriptions.items.append(description)
    event = default_event_record()
    event.flags = make_raw_bitset(1, 4)
    event.value = make_raw_u32(8)
    effect.events.items.append(event)
    resource.effect_descriptions.items.append(effect)

    diagnostics = validate_resource(resource)
    codes = {d.code for d in diagnostics}

    assert codes == {"dangling_component_target", "dangling_shake_target"}


def test_commit_rejects_semantic_errors():
    resource = default_resource()
    resource.effect_name_map.items.append(
        StringU32Pair(name=WireString.from_text("broken"), target=make_raw_u32(4))
    )
    session = EditorSession(
        handle=ResourceHandle(package_path="", tgi=""),
        source=LocalFileEffDirSource(),
        original_bytes=b"",
        working=resource,
    )

    try:
        api.commit(session)
    except api.ValidationError as error:
        assert error.diagnostics[0].code == "dangling_effect_target"
    else:
        raise AssertionError("commit accepted an invalid effect target")
