import struct

from effdir_editor.container import qfs
from effdir_editor.container.adapter import DbpfEffDirSource, ResourceHandle, WriteOptions
from effdir_editor.container.dbpf import (
    COMPRESSION_DIR_TGI,
    DbpfArchive,
    Tgi,
    create_archive_and_save,
    replace_entry_and_save,
)

TARGET = Tgi(0xEA5118B0, 0xEA5118B1, 1)


def _single_entry_dbpf(tgi: Tgi, payload: bytes) -> bytes:
    payload_offset = 96
    index_offset = payload_offset + len(payload)
    header = bytearray(96)
    header[:4] = b"DBPF"
    struct.pack_into(
        "<14I",
        header,
        4,
        1,
        0,
        0,
        0,
        0,
        1,
        2,
        7,
        1,
        index_offset,
        20,
        0,
        0,
        0,
    )
    index = struct.pack("<5I", tgi.type_id, tgi.group_id, tgi.instance_id, payload_offset, len(payload))
    return bytes(header) + payload + index


def test_dbpf_compressed_write_reopens_and_preserves_compression_by_default(tmp_path):
    source = tmp_path / "source.dat"
    compressed_output = tmp_path / "compressed.dat"
    preserved_output = tmp_path / "preserved.dat"
    source.write_bytes(_single_entry_dbpf(TARGET, b"original"))
    first_payload = (b"effect-particle-curve\0" * 300) + bytes(range(64))

    assert replace_entry_and_save(source, compressed_output, TARGET, first_payload, compress=True) == []
    archive = DbpfArchive.open(compressed_output)
    raw = archive.read_raw(TARGET)
    assert archive.is_compressed(TARGET)
    assert struct.unpack_from("<I", raw)[0] == len(raw) - 4
    assert qfs.is_compressed(raw[4:])
    assert archive.read_decompressed(TARGET) == first_payload

    second_payload = b"replacement-" * 500
    assert replace_entry_and_save(compressed_output, preserved_output, TARGET, second_payload) == []
    reopened = DbpfArchive.open(preserved_output)
    assert reopened.is_compressed(TARGET)
    assert reopened.read_decompressed(TARGET) == second_payload


def test_dbpf_falls_back_to_raw_when_compression_safety_check_fails(tmp_path, monkeypatch):
    source = tmp_path / "source.dat"
    output = tmp_path / "output.dat"
    payload = b"safe payload" * 50
    source.write_bytes(_single_entry_dbpf(TARGET, b"original"))
    monkeypatch.setattr(qfs, "decompress", lambda _encoded: b"wrong")

    warnings = replace_entry_and_save(source, output, TARGET, payload, compress=True)
    archive = DbpfArchive.open(output)

    assert warnings and "safety check failed" in warnings[0]
    assert not archive.is_compressed(TARGET)
    assert archive.read_raw(TARGET) == payload


def test_create_single_resource_dbpf_uncompressed(tmp_path):
    output = tmp_path / "single.dat"
    payload = b"standalone EFFDIR"

    assert create_archive_and_save(output, TARGET, payload) == []
    archive = DbpfArchive.open(output)

    assert [entry.tgi for entry in archive.list_entries()] == [TARGET]
    assert not archive.is_compressed(TARGET)
    assert archive.read_decompressed(TARGET) == payload


def test_create_single_resource_dbpf_compressed(tmp_path):
    output = tmp_path / "single-compressed.dat"
    payload = b"compressed standalone EFFDIR" * 200

    result = DbpfEffDirSource().write(
        ResourceHandle(package_path="", tgi=str(TARGET)),
        payload,
        WriteOptions(output_path=str(output), compress=True, create_package=True),
    )
    archive = DbpfArchive.open(output)

    assert result.path == str(output)
    assert result.warnings == ()
    assert [entry.tgi for entry in archive.list_entries()] == [TARGET, Tgi(*COMPRESSION_DIR_TGI)]
    assert archive.is_compressed(TARGET)
    assert archive.read_decompressed(TARGET) == payload
