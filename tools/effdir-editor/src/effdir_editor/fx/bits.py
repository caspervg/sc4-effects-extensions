"""One-line bit test shared by every emitter that reads a `bitset<N>`
`Raw[int]` field (particle flags_0/1/2, decal flags, effect flags, ...)."""

from __future__ import annotations


def bit(value: int, n: int) -> bool:
    return (int(value) >> n) & 1 == 1
