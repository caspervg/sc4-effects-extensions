"""QFS/RefPack compression, as used by DBPF entries (SimCity 4 et al.).

Signature: 2-byte header, high bit of byte0 (0x80) selects a 4-byte
big-endian decompressed-size field instead of 3-byte. Compressed size is
tracked by the DBPF index entry, not by this stream.
"""

from __future__ import annotations

MAGIC_BYTE1 = 0x10
MAGIC_BYTE2 = 0xFB


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
                out.extend(data[pos : pos + plain_len])
                pos += plain_len
            break

        if ch0 >= 0xE0:
            plain_len = ((ch0 & 0x1F) << 2) + 4
            pos += 1
            out.extend(data[pos : pos + plain_len])
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
            out.extend(data[pos : pos + plain_len])
            pos += plain_len

        copy_start = len(out) - copy_offset
        if copy_start < 0:
            raise QfsError(f"back-reference offset {copy_offset} exceeds output length {len(out)}")
        for i in range(copy_len):
            out.append(out[copy_start + i])

    if len(out) != decompressed_size:
        raise QfsError(f"decompressed {len(out)} bytes, header declared {decompressed_size}")
    return bytes(out)
