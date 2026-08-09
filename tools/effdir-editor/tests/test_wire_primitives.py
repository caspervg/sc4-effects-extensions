import struct

import pytest

from effdir_editor.wire import Vec3
from effdir_editor.wire.cursor import CursorError, ReadCursor, WriteCursor
from effdir_editor.wire.strings import (
    decode_string_length,
    encode_string_length,
    read_wire_string,
    write_wire_string,
    WireString,
)
from effdir_editor.wire.types import make_raw_f32, make_raw_u32, read_f32, read_u32, write_raw
from effdir_editor.wire.vectors import read_vector, write_vector
from effdir_editor.model.components import (
    default_scrubber,
    default_sound,
    read_camera,
    read_sequence,
    read_sound,
)
from effdir_editor.model.particle import default_particle
from effdir_editor.model.effect import default_description_record
from effdir_editor.editor.nodes import child_paths


def test_scalar_round_trip():
    w = WriteCursor()
    w.u8(0x12)
    w.u16(0x3456)
    w.u32(0x789ABCDE)
    w.f32(1.5)
    r = ReadCursor(w.getvalue())
    assert r.u8() == 0x12
    assert r.u16() == 0x3456
    assert r.u32() == 0x789ABCDE
    assert r.f32() == 1.5
    assert r.at_end()


def test_truncated_read_raises():
    r = ReadCursor(b"\x01\x02")
    with pytest.raises(CursorError):
        r.u32()


# --- packed EFFDIR string framing -----------------------------------------
#
# Runtime evidence from the vanilla EFFDIR uses a little-endian u32 length,
# despite effdir-editor-spec.md's stale description of a generic 7-bit
# continuation helper used by another stream call site. See strings.py's
# module-level evidence note.


@pytest.mark.parametrize(
    "n,expected_bytes",
    [
        (0, bytes.fromhex("00 00 00 00")),
        (1, bytes.fromhex("01 00 00 00")),
        (127, bytes.fromhex("7F 00 00 00")),
        (128, bytes.fromhex("80 00 00 00")),
        (300, bytes.fromhex("2C 01 00 00")),
    ],
)
def test_string_length_encoding_matches_effdir_runtime_format(n, expected_bytes):
    assert encode_string_length(n) == expected_bytes


@pytest.mark.parametrize("n", [0, 1, 2, 127, 128, 129, 300, 16384, 16383, 2_097_151, 2_097_152])
def test_string_length_round_trip(n):
    encoded = encode_string_length(n)
    cursor = ReadCursor(encoded)
    assert decode_string_length(cursor) == n
    assert cursor.at_end()


def test_string_has_no_terminator_and_no_conversion():
    s = WireString.from_raw_bytes(b"hello")
    w = WriteCursor()
    write_wire_string(w, s)
    # u32 length (5) + 5 payload bytes, no trailing NUL
    assert w.getvalue() == bytes.fromhex("05 00 00 00") + b"hello"

    r = ReadCursor(w.getvalue())
    decoded = read_wire_string(r)
    assert decoded.raw_bytes == b"hello"
    assert decoded.decoded == "hello"
    assert decoded.valid is True
    assert r.at_end()


def test_string_preserves_invalid_utf8_bytes():
    raw_payload = b"\xff\xfe\x00\x01"
    w = WriteCursor()
    w.raw(encode_string_length(len(raw_payload)))
    w.raw(raw_payload)
    r = ReadCursor(w.getvalue())
    s = read_wire_string(r)
    assert s.valid is False
    assert s.decoded is None
    assert s.raw_bytes == raw_payload
    assert s.encoding == "raw_bytes"


def test_empty_string_round_trip():
    w = WriteCursor()
    write_wire_string(w, WireString.from_text(""))
    assert w.getvalue() == b"\x00\x00\x00\x00"
    r = ReadCursor(w.getvalue())
    s = read_wire_string(r)
    assert s.raw_bytes == b""
    assert s.decoded == ""


# --- Raw[T] invariant: raw_bytes always encodes value ---------------------


def test_raw_replace_recomputes_bytes():
    raw = make_raw_u32(10)
    replaced = raw.replace(20)
    assert replaced.value == 20
    assert replaced.raw_bytes == struct.pack("<I", 20)
    assert replaced.source_span is None


def test_raw_write_emits_verbatim_bytes():
    raw = make_raw_f32(float("nan"))
    w = WriteCursor()
    write_raw(w, raw)
    assert w.getvalue() == raw.raw_bytes


def test_read_raw_round_trip_preserves_span():
    w = WriteCursor()
    w.u32(42)
    r = ReadCursor(w.getvalue())
    raw = read_u32(r)
    assert raw.value == 42
    assert raw.source_span.start == 0
    assert raw.source_span.end == 4
    assert raw.raw_bytes == struct.pack("<I", 42)


# --- vector<T>: u32 count + elements, no size field ------------------------


def test_vector_round_trip():
    w = WriteCursor()
    vec_items = [1.0, 2.0, 3.0]
    from effdir_editor.wire.vectors import WireVector

    write_vector(w, WireVector(count=len(vec_items), items=vec_items, source_span=None), WriteCursor.f32)
    assert w.getvalue() == struct.pack("<Iiii".replace("iii", "fff"), 3, 1.0, 2.0, 3.0)

    r = ReadCursor(w.getvalue())
    vec = read_vector(r, ReadCursor.f32, element_size=4)
    assert vec.items == [1.0, 2.0, 3.0]
    assert len(vec) == 3
    assert r.at_end()


def test_vector_write_recomputes_count_after_mutation():
    from effdir_editor.wire.vectors import WireVector

    vec = WireVector(count=99, items=[1, 2], source_span=None)
    w = WriteCursor()
    write_vector(w, vec, WriteCursor.u32)
    r = ReadCursor(w.getvalue())
    assert r.u32() == 2  # not the stale count=99


def test_vector_fixed_size_bound_check_rejects_impossible_count():
    w = WriteCursor()
    w.u32(1_000_000)  # count claims a million elements
    w.f32(1.0)  # but only one is actually present
    r = ReadCursor(w.getvalue())
    with pytest.raises(CursorError):
        read_vector(r, ReadCursor.f32, element_size=4)


def test_sequence_option_word_keeps_bitset_type():
    w = WriteCursor()
    w.u16(1)  # marker
    w.u32(0)  # empty item vector
    w.u32(0b101)

    sequence = read_sequence(ReadCursor(w.getvalue()))

    assert sequence.flags.wire_type == "bitset<3>"
    assert sequence.flags.value == 0b101


def test_camera_option_word_keeps_bitset_type():
    w = WriteCursor()
    w.u16(0)  # marker
    w.u32(0b1001)
    w.u8(2)
    w.u8(3)
    w.f32(4.0)

    camera = read_camera(ReadCursor(w.getvalue()))

    assert camera.flags.wire_type == "bitset<4>"
    assert camera.flags.value == 0b1001
    assert camera.zoom.value == 2
    assert camera.rotation.value == 3


def test_sound_option_word_keeps_bitset_type_and_constructor_default():
    w = WriteCursor()
    w.u16(0)
    w.u32(1)
    w.u32(0x12345678)
    w.f32(0.25)
    w.f32(3.0)

    sound = read_sound(ReadCursor(w.getvalue()))

    assert sound.flags.wire_type == "bitset<1>"
    assert sound.flags.value == 1
    assert default_sound().location_update_rate.value == 0.5
    assert default_scrubber().map_value.value == 16.0

    particle = default_particle()
    assert particle.value_164.value == 0
    assert particle.value_166.value == 1
    assert particle.value_168.value == 1.0

    description = default_description_record()
    assert description.shell_count.value == 1
    assert description.shell_offset.value == 16
    assert description.selection_group.value == 0
    assert description.description_index.value == 0xFFFFFFFF
    assert description.legacy_transform.matrix.row_0 == Vec3(1.0, 0.0, 0.0)
    assert description.legacy_transform.matrix.row_1 == Vec3(0.0, 1.0, 0.0)
    assert description.legacy_transform.matrix.row_2 == Vec3(0.0, 0.0, 1.0)


def test_legacy_transform_and_matrix_are_reflected_as_record_children():
    description = default_description_record()

    assert "legacy_transform" in child_paths(description, "")
    assert "legacy_transform.matrix" in child_paths(description, "legacy_transform")
    assert child_paths(description, "legacy_transform.matrix") == [
        "legacy_transform.matrix.row_0",
        "legacy_transform.matrix.row_1",
        "legacy_transform.matrix.row_2",
    ]
