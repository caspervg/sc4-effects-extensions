"""QFS/RefPack compression, as used by DBPF entries (SimCity 4 et al.).

Signature: 2-byte header, high bit of byte0 (0x80) selects a 4-byte
big-endian decompressed-size field instead of 3-byte. Compressed size is
tracked by the DBPF index entry, not by this stream.
"""

from __future__ import annotations

from array import array

MAGIC_BYTE1 = 0x10
MAGIC_BYTE2 = 0xFB

_MAX_SIZE = 0xFFFFFF
_MAX_OFFSET = 131072
_MAX_COPY = 1028
_MIN_MATCH = 3
_HASH_BITS = 16
_HASH_SIZE = 1 << _HASH_BITS
_HASH_MASK = _HASH_SIZE - 1
_MAX_CHAIN = 96
_NICE_MATCH = 256
_MATCH_INSERT_LIMIT = 64


class QfsError(ValueError):
    pass


def is_compressed(data: bytes) -> bool:
    return len(data) >= 2 and data[0] in (0x10, 0x11) and data[1] == MAGIC_BYTE2


def decompress(data: bytes) -> bytes:
    if not is_compressed(data):
        raise QfsError("missing 0x10FB/0x11FB QFS signature")

    pos = 0
    ctrl0 = data[pos]
    pos += 1
    pos += 1  # ctrl1 (0xFB), unused beyond the signature check

    large = bool(ctrl0 & 0x80)
    if large:
        decompressed_size = (data[pos] << 24) | (data[pos + 1] << 16) | (data[pos + 2] << 8) | data[pos + 3]
        pos += 4
    else:
        decompressed_size = (data[pos] << 16) | (data[pos + 1] << 8) | data[pos + 2]
        pos += 3

    out = bytearray()
    n = len(data)
    while pos < n:
        ch0 = data[pos]

        if ch0 >= 0xFC:
            plain_len = ch0 & 0x03
            pos += 1
            if plain_len:
                out.extend(data[pos: pos + plain_len])
                pos += plain_len
            break

        if ch0 >= 0xE0:
            plain_len = ((ch0 & 0x1F) << 2) + 4
            pos += 1
            out.extend(data[pos: pos + plain_len])
            pos += plain_len
            continue

        if ch0 >= 0xC0:
            ch1, ch2, ch3 = data[pos + 1], data[pos + 2], data[pos + 3]
            plain_len = ch0 & 0x03
            copy_len = ((ch0 & 0x0C) << 6) + ch3 + 5
            copy_offset = ((ch0 & 0x10) << 12) + (ch1 << 8) + ch2 + 1
            pos += 4
        elif ch0 >= 0x80:
            ch1, ch2 = data[pos + 1], data[pos + 2]
            plain_len = (ch1 >> 6) & 0x03
            copy_len = (ch0 & 0x3F) + 4
            copy_offset = ((ch1 & 0x3F) << 8) + ch2 + 1
            pos += 3
        else:
            ch1 = data[pos + 1]
            plain_len = ch0 & 0x03
            copy_len = ((ch0 & 0x1C) >> 2) + 3
            copy_offset = ((ch0 & 0x60) << 3) + ch1 + 1
            pos += 2

        if plain_len:
            out.extend(data[pos: pos + plain_len])
            pos += plain_len

        copy_start = len(out) - copy_offset
        if copy_start < 0:
            raise QfsError(f"back-reference offset {copy_offset} exceeds output length {len(out)}")
        for i in range(copy_len):
            out.append(out[copy_start + i])

    if len(out) != decompressed_size:
        raise QfsError(f"decompressed {len(out)} bytes, header declared {decompressed_size}")
    return bytes(out)


def compress(data: bytes) -> bytes:
    """Compress *data* as a QFS/RefPack stream.

    The returned stream starts at the QFS signature.  DBPF's optional
    four-byte compressed-size prefix belongs to the container layer and is
    intentionally not included here.
    """

    source = bytes(data)
    size = len(source)
    if size > _MAX_SIZE:
        raise QfsError(f"QFS supports at most {_MAX_SIZE} uncompressed bytes, got {size}")

    out = bytearray((MAGIC_BYTE1, MAGIC_BYTE2, (size >> 16) & 0xFF, (size >> 8) & 0xFF, size & 0xFF))
    if not source:
        out.append(0xFC)
        return bytes(out)

    # Hash chains retain earlier occurrences of each three-byte prefix.  The
    # bounded search makes encoding linear in practice while still finding
    # long repeated regions in typical EFFDIR payloads.
    previous = array("i", [-1]) * size
    heads = array("i", [-1]) * _HASH_SIZE
    last_hash_pos = size - _MIN_MATCH
    pos = 0
    literal_start = 0

    while pos <= last_hash_pos:
        b0, b1, b2 = source[pos], source[pos + 1], source[pos + 2]
        hash_value = ((b0 << 8) ^ (b1 << 4) ^ b2) & _HASH_MASK
        candidate = heads[hash_value]
        best_len = 0
        best_offset = 0
        best_score = 0

        if candidate >= 0:
            max_len = min(size - pos, _MAX_COPY)
            min_candidate = max(0, pos - _MAX_OFFSET)
            steps = _MAX_CHAIN
            while candidate >= min_candidate and steps:
                steps -= 1
                offset = pos - candidate
                min_len = 3 if offset <= 1024 else 4 if offset <= 16384 else 5
                if max_len >= min_len and source[candidate: candidate + 3] == source[pos: pos + 3]:
                    length = _MIN_MATCH
                    while length < max_len and source[candidate + length] == source[pos + length]:
                        length += 1
                    if length >= min_len:
                        control_size = 2 if length <= 10 and offset <= 1024 else 3 if length <= 67 and offset <= 16384 else 4
                        score = length - control_size
                        if score > best_score or (score == best_score and length > best_len):
                            best_len = length
                            best_offset = offset
                            best_score = score
                            if length == max_len or length >= _NICE_MATCH:
                                break
                candidate = previous[candidate]

        if best_len:
            literal_start = _emit_pending_literals(out, source, literal_start, pos)
            literal_count = pos - literal_start
            _emit_copy_packet(out, source, literal_start, literal_count, best_len, best_offset)

            previous[pos] = heads[hash_value]
            heads[hash_value] = pos
            insert_end = min(pos + best_len, last_hash_pos + 1)
            insert_start = max(pos + 1, insert_end - _MATCH_INSERT_LIMIT)
            for insert_pos in range(insert_start, insert_end):
                insert_hash = (
                                      (source[insert_pos] << 8) ^ (source[insert_pos + 1] << 4) ^ source[insert_pos + 2]
                              ) & _HASH_MASK
                previous[insert_pos] = heads[insert_hash]
                heads[insert_hash] = insert_pos

            pos += best_len
            literal_start = pos
        else:
            previous[pos] = heads[hash_value]
            heads[hash_value] = pos
            pos += 1

    _emit_final_literals(out, source, literal_start, size)
    return bytes(out)


def _emit_pending_literals(out: bytearray, data: bytes, start: int, end: int) -> int:
    attached = (end - start) & 0x03
    flush_end = end - attached
    _emit_literal_runs(out, data, start, flush_end)
    return flush_end


def _emit_final_literals(out: bytearray, data: bytes, start: int, end: int) -> None:
    terminal = (end - start) & 0x03
    flush_end = end - terminal
    _emit_literal_runs(out, data, start, flush_end)
    out.append(0xFC | terminal)
    out.extend(data[flush_end:end])


def _emit_literal_runs(out: bytearray, data: bytes, start: int, end: int) -> None:
    pos = start
    while pos < end:
        chunk = min(112, end - pos)
        out.append(0xE0 | ((chunk - 4) >> 2))
        out.extend(data[pos: pos + chunk])
        pos += chunk


def _emit_copy_packet(
        out: bytearray,
        data: bytes,
        literal_start: int,
        literal_count: int,
        copy_len: int,
        copy_offset: int,
) -> None:
    offset = copy_offset - 1
    if copy_offset <= 1024 and copy_len <= 10:
        out.append(((offset >> 8) << 5) | ((copy_len - 3) << 2) | literal_count)
        out.append(offset & 0xFF)
    elif copy_offset <= 16384 and copy_len <= 67:
        out.append(0x80 | (copy_len - 4))
        out.append((literal_count << 6) | ((offset >> 8) & 0x3F))
        out.append(offset & 0xFF)
    else:
        length = copy_len - 5
        out.append(0xC0 | literal_count | ((length >> 8) << 2) | ((offset >> 16) << 4))
        out.append((offset >> 8) & 0xFF)
        out.append(offset & 0xFF)
        out.append(length & 0xFF)
    out.extend(data[literal_start: literal_start + literal_count])
