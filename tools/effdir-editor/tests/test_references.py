from types import SimpleNamespace

from effdir_editor.editor.references import build_reference_index


def _value(value):
    return SimpleNamespace(value=value)


def _name(value):
    return SimpleNamespace(decoded=value)


def _vector(*items):
    return SimpleNamespace(items=list(items))


def test_event_descriptor_indices_create_component_backlinks():
    events = _vector(
        SimpleNamespace(flags=_value(1 << 0), name=_name("quake"), value=_value(1)),
        SimpleNamespace(flags=_value((1 << 1) | (1 << 2)), name=_name("flash"), value=_value(0)),
        SimpleNamespace(flags=_value(1 << 3), name=_name("tint"), value=_value(0)),
    )
    resource = SimpleNamespace(
        effect_name_map=_vector(SimpleNamespace(name=_name("owner"), target=_value(0))),
        effect_key_map=_vector(),
        message_triggers=_vector(),
        effect_descriptions=_vector(SimpleNamespace(events=events)),
        shakes=_vector(object(), object()),
        lights=_vector(object()),
        components=SimpleNamespace(
            sequences=_vector(),
        ),
    )

    index = build_reference_index(resource)

    assert [ref.path for ref in index.path_backlinks["shakes[1]"]] == [
        "effect_descriptions[0].events[0]"
    ]
    assert [ref.path for ref in index.path_backlinks["lights[0]"]] == [
        "effect_descriptions[0].events[1]",
        "effect_descriptions[0].events[2]",
    ]
    assert "flashEffect" in index.path_backlinks["lights[0]"][0].label
    assert "tintEffect" in index.path_backlinks["lights[0]"][1].label


def test_out_of_range_event_descriptor_index_is_not_linked():
    resource = SimpleNamespace(
        effect_name_map=_vector(),
        effect_key_map=_vector(),
        message_triggers=_vector(),
        effect_descriptions=_vector(
            SimpleNamespace(
                events=_vector(
                    SimpleNamespace(flags=_value(1 << 0), name=_name("bad"), value=_value(7))
                )
            )
        ),
        shakes=_vector(),
        lights=_vector(),
        components=SimpleNamespace(sequences=_vector()),
    )

    assert build_reference_index(resource).path_backlinks == {}
