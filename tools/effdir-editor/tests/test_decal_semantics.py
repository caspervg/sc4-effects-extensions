from effdir_editor.model.decal import default_decal, effective_flags, effective_repeat_mode
from effdir_editor.wire import make_raw_bitset, make_raw_u8


def test_default_decal_exposes_runtime_normalization_without_mutating_wire_values():
    descriptor = default_decal()

    assert descriptor.repeat_mode.value == 0
    assert descriptor.flags.value == 0
    assert effective_repeat_mode(descriptor) == 2
    assert effective_flags(descriptor) == 1 << 6
    assert descriptor.repeat_mode.value == 0
    assert descriptor.flags.value == 0


def test_nonzero_decal_mode_does_not_synthesize_static_flag():
    descriptor = default_decal()
    descriptor.repeat_mode = make_raw_u8(3)
    descriptor.flags = make_raw_bitset(1 << 2, 7)

    assert effective_repeat_mode(descriptor) == 3
    assert effective_flags(descriptor) == 1 << 2
