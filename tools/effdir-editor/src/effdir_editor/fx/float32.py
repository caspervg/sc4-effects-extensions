"""Single-precision helpers shared by the compiler and the decompiler.

Every game float is IEEE single, so "does this source text reproduce
that field" means an exact bit comparison after the same single-precision
steps the game's parsers perform. Keeping those steps here lets the
decompiler check a candidate spelling against the compiler's own arithmetic.
"""

from __future__ import annotations

import math
import struct
from typing import Callable, Optional, Tuple

from ..wire import Vec3


def f32(value: float) -> float:
    """Round to single precision, the storage of every game float."""

    try:
        return struct.unpack("<f", struct.pack("<f", value))[0]
    except OverflowError:
        return math.inf if value > 0 else -math.inf


def next_f32(value: float, steps: int = 1) -> float:
    """`value` moved `steps` single-precision steps (negative steps go down)."""

    bits = struct.unpack("<i", struct.pack("<f", value))[0]
    if bits < 0:
        bits = -(bits & 0x7FFFFFFF)
    bits += steps
    if bits < 0:
        bits = (-bits) | 0x80000000
    return struct.unpack("<f", struct.pack("<I", bits & 0xFFFFFFFF))[0]


def normalized(v: Vec3, order: str = "xyz") -> Vec3:
    """Unit vector the way the Windows parsers compute it: the inverse length
    times each component, with the x87 running in single precision.

    Every step (`fmul`, `fadd`, `fsqrt`, `fdiv`) rounds to 24 bits, so the
    order of the squared terms matters. `order` is the order the parser adds
    them in (`-alpha`: xyz, `-dir` and `-wind`: zyx, `-velocity`: yzx,
    `-vel`: xyz, read from `0x0059B680`, `0x0059C280`, `0x0059A820`). The
    instructions keep the inverse in a register, so the rounded inverse
    that vanilla's values require can only come from the x87 precision
    control. The CRT sets 53 bits at startup (`__setdefaultprecision`), and
    records 85 and 457 of the vanilla resource are unreachable at 53 bits, so
    the 24-bit state is inferred (Direct3D setup is the usual cause, and
    nothing in the parser sets it).
    """

    values = {"x": v.x, "y": v.y, "z": v.z}
    total = 0.0
    for index, axis in enumerate(order):
        square = f32(values[axis] * values[axis])
        total = square if index == 0 else f32(total + square)
    if total <= 0.0:
        return Vec3(0.0, 0.0, 0.0)
    inverse = f32(1.0 / f32(math.sqrt(total)))
    return Vec3(f32(v.x * inverse), f32(v.y * inverse), f32(v.z * inverse))


_TAU32 = f32(2.0 * math.pi)


def rotate(matrix, axis: str, turns: float) -> None:
    """`cS3DMatrix3::RotateX/Y/Z`: post-multiply, text angles in turns."""

    # `fsin`/`fcos` take the product of `fmul`, which the 24-bit x87 has
    # already rounded to single precision (0x005989D0).
    angle = f32(turns * _TAU32)
    c = f32(math.cos(angle))
    s = f32(math.sin(angle))
    rows = [matrix.row_0, matrix.row_1, matrix.row_2]
    columns = [[rows[i].x for i in range(3)], [rows[i].y for i in range(3)], [rows[i].z for i in range(3)]]
    if axis == "x":
        first, second = columns[1], columns[2]
        columns[1] = [f32(s * b + c * a) for a, b in zip(first, second)]
        columns[2] = [f32(b * c + a * -s) for a, b in zip(first, second)]
    elif axis == "y":
        first, second = columns[0], columns[2]
        columns[0] = [f32(a * c + b * -s) for a, b in zip(first, second)]
        columns[2] = [f32(s * a + c * b) for a, b in zip(first, second)]
    else:
        first, second = columns[0], columns[1]
        columns[0] = [f32(s * b + c * a) for a, b in zip(first, second)]
        columns[1] = [f32(b * c + a * -s) for a, b in zip(first, second)]
    matrix.row_0 = Vec3(columns[0][0], columns[1][0], columns[2][0])
    matrix.row_1 = Vec3(columns[0][1], columns[1][1], columns[2][1])
    matrix.row_2 = Vec3(columns[0][2], columns[1][2], columns[2][2])


def shortest_decimal(value: float, *, check: Optional[Callable[[float], bool]] = None) -> str:
    """Shortest fixed-notation decimal that parses back to `value`.

    With `check`, the text must also satisfy it after parsing to single
    precision, for spellings where the parser transforms the value.
    """

    if value == 0.0:
        return "-0" if math.copysign(1.0, value) < 0 else "0"
    single = f32(value)
    for precision in range(1, 18):
        text = f"{single:.{precision}g}"
        parsed = f32(float(text))
        if check(parsed) if check is not None else parsed == single:
            break
    else:
        text = f"{single:.17g}"
    if "e" in text or "E" in text:
        from decimal import Decimal

        text = format(Decimal(text), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def bits(value: float) -> bytes:
    """The single-precision bit pattern, which is the comparison that keeps
    `-0.0` distinct from `0.0`."""

    return struct.pack("<f", value)


def nearby_singles(value: float, steps: int = 3):
    """`value` and its nearest single-precision neighbours, closest first."""

    yield value
    for step in range(1, steps + 1):
        yield next_f32(value, step)
        yield next_f32(value, -step)


def fit_unit(vector: Vec3, order: str = "xyz") -> Optional[Vec3]:
    """A vector that normalizes to exactly `vector`, or None.

    The stored value is what `normalized` returned, and passing it back can
    shift a component by a unit in the last place. Try the value itself,
    then single-precision neighbours of it at simple scales. The radius
    shrinks with the number of nonzero components to bound the search.
    """

    def matches(candidate: Vec3) -> bool:
        result = normalized(candidate, order)
        return (bits(result.x), bits(result.y), bits(result.z)) == (bits(vector.x), bits(vector.y), bits(vector.z))

    if matches(vector):
        return vector
    nonzero = sum(1 for c in (vector.x, vector.y, vector.z) if c != 0.0)
    radius = {0: 0, 1: 96, 2: 40, 3: 6}[nonzero]
    for scale in (1.0, 0.5, 2.0, 0.25, 4.0, 0.1, 10.0, 0.2, 5.0, 3.0):
        center = Vec3(f32(vector.x * scale), f32(vector.y * scale), f32(vector.z * scale))
        xs = list(nearby_singles(center.x, radius if center.x != 0.0 else 0))
        ys = list(nearby_singles(center.y, radius if center.y != 0.0 else 0))
        zs = list(nearby_singles(center.z, radius if center.z != 0.0 else 0))
        for x in xs:
            for y in ys:
                for z in zs:
                    candidate = Vec3(x, y, z)
                    if matches(candidate):
                        return candidate
    return None


def fit_base_vary(low: float, high: float) -> Tuple[float, float, bool]:
    """Find `base` and `vary` singles with `f32(base-vary)==low` and
    `f32(base+vary)==high`, the shape `life`, `-speed`, and randomWalk
    `-delay`/`-strength` store. The last value is False when only an
    approximate pair exists."""

    low, high = f32(low), f32(high)
    if low == high:
        return low, 0.0, True
    base = f32((low + high) / 2.0)
    vary = f32((high - low) / 2.0)
    for b in nearby_singles(base):
        for v in nearby_singles(vary):
            if f32(b - v) == low and f32(b + v) == high:
                return b, v, True
    return base, vary, False
