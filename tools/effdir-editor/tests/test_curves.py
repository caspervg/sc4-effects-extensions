from effdir_editor.editor.curves import curve_info
from effdir_editor.editor.nodes import build_node
from effdir_editor.editor.references import build_reference_index
from effdir_editor.model.decal import default_decal
from effdir_editor.model.light import default_light
from effdir_editor.model.particle import default_particle
from effdir_editor.model.resource import default_resource
from effdir_editor.model.shake import default_shake


def test_curve_info_accepts_bound_scalar_vectors_only():
    resource = default_resource()
    resource.particles.items.append(default_particle())
    references = build_reference_index(resource)

    curve = build_node(resource, "particles[0].emit_curve", reference_index=references)
    records = build_node(resource, "particles[0].wiggles", reference_index=references)

    info = curve_info(curve)

    assert info is not None
    assert info.path == "particles[0].emit_curve"
    assert "emit" in info.commands
    assert curve_info(records) is None


def test_curve_info_covers_unlisted_scalar_curve_fields():
    resource = default_resource()
    resource.particles.items.append(default_particle())
    resource.decals.items.append(default_decal())
    resource.shakes.items.append(default_shake())
    resource.lights.items.append(default_light())
    references = build_reference_index(resource)

    paths = (
        "particles[0].alpha_curve",
        "particles[0].size_curve",
        "particles[0].aspect_curve",
        "particles[0].rotate_curve",
        "particles[0].alpha_warp_curve",
        "particles[0].attractor_curve",
        "particles[0].explosion_curve",
        "decals[0].rotation",
        "decals[0].size",
        "decals[0].alpha",
        "decals[0].aspect",
        "shakes[0].amplitude",
        "shakes[0].frequency",
        "lights[0].strength",
    )

    for path in paths:
        assert curve_info(build_node(resource, path, reference_index=references)) is not None
