from effdir_editor.bindings.catalog import CATALOG, Transform


def test_catalog_transforms_use_structured_values():
    assert all(
        isinstance(transform, Transform)
        for binding in CATALOG
        for transform in binding.transforms
    )
