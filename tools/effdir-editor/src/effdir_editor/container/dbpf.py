"""Layer 1: DBPF container -- locate a resource by TGI, decompress its
payload if needed, hand raw bytes to callers. Never interprets the bytes
it returns.

Header layout (96 bytes) and 20-byte index entries per the task spec
(DBPF v1.x, index major version 7). Compression directory TGI
E86B1EEF-E86B1EEF-286B1F03 holds back-to-back 16-byte records
(type, group, instance, uncompressed_size); listed TGIs are QFS/RefPack
compressed on disk (see container/qfs.py).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import qfs

MAGIC = b"DBPF"
HEADER_SIZE = 96
INDEX_ENTRY_SIZE = 20
COMPRESSION_DIR_TGI = (0xE86B1EEF, 0xE86B1EEF, 0x286B1F03)


class DbpfError(ValueError):
    pass


@dataclass(frozen=True)
class Tgi:
    type_id: int
    group_id: int
    instance_id: int

    @classmethod
    def parse(cls, s: str) -> "Tgi":
        parts = s.split("-")
        if len(parts) != 3:
            raise DbpfError(f"malformed TGI string: {s!r}")
        try:
            t, g, i = (int(p, 16) for p in parts)
        except ValueError as exc:
            raise DbpfError(f"malformed TGI string: {s!r}") from exc
        return cls(t, g, i)

    # alias per spec wording ("from_string/parse classmethod")
    from_string = parse

    def __str__(self) -> str:
        return f"{self.type_id:08X}-{self.group_id:08X}-{self.instance_id:08X}"


@dataclass(frozen=True)
class IndexEntry:
    tgi: Tgi
    offset: int
    size: int


@dataclass(frozen=True)
class DbpfHeader:
    major_version: int
    minor_version: int
    user_major_version: int
    user_minor_version: int
    flags: int
    date_created: int
    date_modified: int
    index_major_version: int
    index_entry_count: int
    index_offset: int
    index_size: int
    hole_entry_count: int
    hole_offset: int
    hole_size: int


def _parse_header(data: bytes) -> DbpfHeader:
    if len(data) < HEADER_SIZE or data[0:4] != MAGIC:
        raise DbpfError("not a DBPF file (bad magic)")
    fields = struct.unpack_from("<14I", data, 4)
    (
        major_version,
        minor_version,
        user_major_version,
        user_minor_version,
        flags,
        date_created,
        date_modified,
        index_major_version,
        index_entry_count,
        index_offset,
        index_size,
        hole_entry_count,
        hole_offset,
        hole_size,
    ) = fields
    return DbpfHeader(
        major_version=major_version,
        minor_version=minor_version,
        user_major_version=user_major_version,
        user_minor_version=user_minor_version,
        flags=flags,
        date_created=date_created,
        date_modified=date_modified,
        index_major_version=index_major_version,
        index_entry_count=index_entry_count,
        index_offset=index_offset,
        index_size=index_size,
        hole_entry_count=hole_entry_count,
        hole_offset=hole_offset,
        hole_size=hole_size,
    )


def _parse_index(data: bytes, header: DbpfHeader) -> list[IndexEntry]:
    entries: list[IndexEntry] = []
    base = header.index_offset
    n = len(data)
    for i in range(header.index_entry_count):
        off = base + i * INDEX_ENTRY_SIZE
        if off + INDEX_ENTRY_SIZE > n:
            raise DbpfError(f"index entry {i} extends past end of file")
        type_id, group_id, instance_id, file_offset, file_size = struct.unpack_from("<5I", data, off)
        if file_offset + file_size > n:
            raise DbpfError(
                f"index entry {i} (TGI {type_id:08X}-{group_id:08X}-{instance_id:08X}) "
                f"offset+size {file_offset + file_size} exceeds file length {n}"
            )
        entries.append(IndexEntry(tgi=Tgi(type_id, group_id, instance_id), offset=file_offset, size=file_size))
    return entries


def _parse_compression_directory(entries: dict[Tgi, "IndexEntry"], data: bytes) -> dict[Tgi, int]:
    dir_tgi = Tgi(*COMPRESSION_DIR_TGI)
    entry = entries.get(dir_tgi)
    if entry is None:
        return {}
    payload = data[entry.offset : entry.offset + entry.size]
    result: dict[Tgi, int] = {}
    for off in range(0, len(payload) - len(payload) % 16, 16):
        type_id, group_id, instance_id, uncompressed_size = struct.unpack_from("<4I", payload, off)
        result[Tgi(type_id, group_id, instance_id)] = uncompressed_size
    return result


class DbpfArchive:
    def __init__(self, data: bytes, header: DbpfHeader, entries: list[IndexEntry]):
        self._data = data
        self._header = header
        self._entries = entries
        self._by_tgi: dict[Tgi, IndexEntry] = {e.tgi: e for e in entries}
        self._compression_dir = _parse_compression_directory(self._by_tgi, data)

    @classmethod
    def open(cls, path: str) -> "DbpfArchive":
        data = Path(path).read_bytes()
        header = _parse_header(data)
        entries = _parse_index(data, header)
        return cls(data, header, entries)

    @property
    def header(self) -> DbpfHeader:
        return self._header

    def list_entries(self) -> list[IndexEntry]:
        return list(self._entries)

    def find(self, tgi: Tgi) -> Optional[IndexEntry]:
        return self._by_tgi.get(tgi)

    def read_raw(self, tgi: Tgi) -> bytes:
        entry = self.find(tgi)
        if entry is None:
            raise DbpfError(f"TGI not found: {tgi}")
        return self._data[entry.offset : entry.offset + entry.size]

    def is_compressed(self, tgi: Tgi) -> bool:
        return tgi in self._compression_dir

    def read_decompressed(self, tgi: Tgi) -> bytes:
        raw = self.read_raw(tgi)
        if not self.is_compressed(tgi):
            return raw
        # DBPF wraps the QFS stream with a leading 4-byte "compressed size
        # including this field" word before the 0x10FB/0x11FB signature
        # (self-describing length, redundant with the index's file_size).
        # Not every producer includes it, so detect rather than assume.
        if qfs.is_compressed(raw):
            return qfs.decompress(raw)
        if len(raw) > 4 and qfs.is_compressed(raw[4:]):
            return qfs.decompress(raw[4:])
        raise qfs.QfsError(
            f"TGI {tgi} is listed as compressed but no QFS signature was found "
            f"at offset 0 or 4 of its {len(raw)}-byte entry"
        )


def replace_entry_and_save(path_in: str, path_out: str, tgi: Tgi, new_uncompressed_bytes: bytes) -> None:
    """Replace `tgi`'s payload with `new_uncompressed_bytes`, stored
    uncompressed; drop it from the compression directory if listed; write a
    complete valid DBPF file (fresh index, recomputed offsets/sizes) to
    path_out. All other entries' bytes are preserved byte-for-byte, in
    their original relative order. Header dates/versions are preserved
    from the source; index-related header fields are recomputed."""

    archive = DbpfArchive.open(path_in)
    dir_tgi = Tgi(*COMPRESSION_DIR_TGI)

    new_payloads: dict[Tgi, bytes] = {}
    for entry in archive.list_entries():
        if entry.tgi == tgi:
            continue
        if entry.tgi == dir_tgi:
            continue  # rebuilt below
        new_payloads[entry.tgi] = archive.read_raw(entry.tgi)

    new_payloads[tgi] = bytes(new_uncompressed_bytes)

    if archive._compression_dir:
        remaining = {t: size for t, size in archive._compression_dir.items() if t != tgi}
        if remaining:
            dir_payload = bytearray()
            for t, size in remaining.items():
                dir_payload += struct.pack("<4I", t.type_id, t.group_id, t.instance_id, size)
            new_payloads[dir_tgi] = bytes(dir_payload)

    # Preserve original entry order (by original file offset) for entries
    # that still exist; the replaced/new tgi keeps its original position if
    # it existed, else is appended; the compression directory (if rebuilt)
    # keeps its original position, else is dropped entirely.
    ordered_tgis: list[Tgi] = []
    for entry in sorted(archive.list_entries(), key=lambda e: e.offset):
        if entry.tgi in new_payloads and entry.tgi not in ordered_tgis:
            ordered_tgis.append(entry.tgi)
    if tgi not in ordered_tgis:
        ordered_tgis.append(tgi)

    header = archive.header
    out = bytearray()
    out += MAGIC
    out += struct.pack(
        "<14I",
        header.major_version,
        header.minor_version,
        header.user_major_version,
        header.user_minor_version,
        header.flags,
        header.date_created,
        header.date_modified,
        header.index_major_version,
        0,  # index_entry_count, patched below
        0,  # index_offset, patched below
        0,  # index_size, patched below
        0,  # hole_entry_count: holes are not reconstructed by this writer
        0,  # hole_offset
        0,  # hole_size
    )
    out += bytes(HEADER_SIZE - len(out))

    new_entries: list[IndexEntry] = []
    for t in ordered_tgis:
        payload = new_payloads[t]
        offset = len(out)
        out += payload
        new_entries.append(IndexEntry(tgi=t, offset=offset, size=len(payload)))

    index_offset = len(out)
    for e in new_entries:
        out += struct.pack("<5I", e.tgi.type_id, e.tgi.group_id, e.tgi.instance_id, e.offset, e.size)
    index_size = len(out) - index_offset

    struct.pack_into("<I", out, 36, len(new_entries))
    struct.pack_into("<I", out, 40, index_offset)
    struct.pack_into("<I", out, 44, index_size)

    Path(path_out).write_bytes(bytes(out))
