from types import SimpleNamespace

from effdir_editor.editor.references import Reference, build_reference_index, reference_info


def _value(value):
    return SimpleNamespace(value=value)


def _name(value):
    return SimpleNamespace(decoded=value)


def _vector(*items):
    return SimpleNamespace(items=list(items))


def test_reference_info_does_not_repeat_effect_description_path():
    reference = Reference(
        path="effect_descriptions[61].descriptions[0]",
        label=(
            'effect_descriptions[61] "plopmode_education_plop" '
            'description[0] "education_coverage_circle_plop_collapse_normal" (component)'
        ),
    )

    assert reference_info(reference) == (
        'effect "plopmode_education_plop" · description '
        '"education_coverage_circle_plop_collapse_normal" (component)'
    )


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
    assert [ref.path for ref in index.outgoing["effect_descriptions[0].events[0]"]] == [
        "shakes[1]"
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


def test_description_records_link_to_verified_component_collections():
    description = SimpleNamespace(
        name=_name("particle child"),
        component_type=_value(0),
        description_index=_value(1),
    )
    resource = SimpleNamespace(
        effect_name_map=_vector(SimpleNamespace(name=_name("owner"), target=_value(0))),
        effect_key_map=_vector(),
        message_triggers=_vector(),
        effect_descriptions=_vector(SimpleNamespace(descriptions=_vector(description), events=_vector())),
        particles=_vector(object(), object()),
        decals=_vector(),
        shakes=_vector(),
        lights=_vector(),
        dynamic_particles=_vector(),
        components=SimpleNamespace(
            brushes=_vector(),
            attractors=_vector(),
            scrubbers=_vector(),
            sequences=_vector(),
            sounds=_vector(),
            cameras=_vector(),
        ),
    )

    index = build_reference_index(resource)

    reference = index.path_backlinks["particles[1]"][0]
    assert reference.path == "effect_descriptions[0].descriptions[0]"
    assert "particle" in reference.label
    outgoing = index.outgoing["effect_descriptions[0].descriptions[0]"][0]
    assert outgoing.path == "particles[1]"
    assert outgoing.kind == "Component"
    owner_outgoing = index.outgoing["effect_descriptions[0]"][0]
    assert owner_outgoing.path == "particles[1]"
    assert owner_outgoing.kind == "Component"
    assert "description[0]" in owner_outgoing.label
