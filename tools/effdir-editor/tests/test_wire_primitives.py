import struct

import pytest

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


# --- string length prefix, per effdir-editor-spec.md "String contract" ---


@pytest.mark.parametrize(
    "n,expected_bytes",
    [
        (0, bytes([0x00])),
        (1, bytes([0x01])),
        (127, bytes([0x7F])),
        (128, bytes([0x80, 0x01])),
        (300, bytes([0xAC, 0x02])),
    ],
)
def test_string_length_encoding_matches_spec_examples(n, expected_bytes):
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
    # length byte (5) + 5 payload bytes, no trailing NUL
    assert w.getvalue() == bytes([5]) + b"hello"

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
    assert w.getvalue() == b"\x00"
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
