import random

import pytest

from effdir_editor.container import qfs


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"a",
        b"ab",
        b"abc",
        b"abcd",
        b"x" * 3,
        b"x" * 10,
        b"x" * 67,
        b"x" * 1028,
        (b"particle-effect-" * 400) + bytes(range(256)) * 4,
        random.Random(0x5C4).randbytes(8192),
    ],
)
def test_compress_decompress_round_trip(payload):
    encoded = qfs.compress(payload)

    assert qfs.is_compressed(encoded)
    assert qfs.decompress(encoded) == payload


def test_compressor_finds_repetitions_at_long_offsets():
    rng = random.Random(641)
    prefix = rng.randbytes(20_000)
    repeated = prefix[100:900] * 8
    payload = prefix + repeated

    encoded = qfs.compress(payload)

    assert qfs.decompress(encoded) == payload
    assert len(encoded) < len(payload)


def test_compressor_rejects_payload_larger_than_refpack_header_limit():
    with pytest.raises(qfs.QfsError, match="at most"):
        qfs.compress(bytes(0x1000000))
