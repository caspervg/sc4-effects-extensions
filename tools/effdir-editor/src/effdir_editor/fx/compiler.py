"""`.fx` source -> `EffDirResource` -> packed EFFDIR bytes.

Each handler below mirrors one command parser of the game (see
`docs/decompiler-semantics.md` and `docs/compiler-defaults.md`). Argument
handling follows `nSCRes::FindSwitchArgumentIndices` and
`FindNonSwitchIndices` (Mac `0x0041BD02`/`0x0041BE46`): positionals end at the
first switch-looking token, a switch takes the tokens up to the next one, a
token starting with `-` or `+` is a switch only when its second character
is a letter (so `-1.5` stays a number), and any switch left unconsumed at the
end is an error.
"""

from __future__ import annotations

import copy
import math
import os
import struct
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from ..model.common import MessageTrigger, StringU32Pair, StringU32U32Record, TimedEffect, TractorPoint, Wiggle
from ..model.components import (
    SequenceItem,
    default_attractor,
    default_brush,
    default_camera,
    default_scrubber,
    default_sequence,
    default_sound,
)
from ..model.decal import DecalDescriptor, default_decal
from ..model.dynamic_particle import DynamicParticleDescriptor, default_dynamic_particle
from ..model.effect import DescriptionRecord, EffectDescription, EventRecord, default_description_record, default_effect_description, default_event_record
from ..model.light import LightDescriptor, default_light
from ..model.particle import ParticleDescriptor, default_particle
from ..model.resource import EffDirResource, TrailingFloatMetadata, default_resource
from ..model.shake import ShakeDescriptor, default_shake
from ..wire import Bounds3, Vec2, Vec3, WireString, WireVector, make_raw_f32, make_raw_u8, make_raw_u16, make_raw_u32
from .float32 import f32, normalized as _normalized, rotate as _rotate
from .parser import Command, FxError, evaluate, expand_includes, parse_file

_PARTICLE_DRAW = {"decal": 0, "decalInvertDepth": 1, "decalIgnoreDepth": 2, "depthDecal": 3, "depthDecalMasked": 4, "additive": 5, "additiveIgnoreDepth": 6, "modulate": 7}
_DECAL_DRAW = {"decal": 0, "additive": 1, "modulate": 2, "decalInvertDepth": 3, "decalNoOverlap": 4}
_ALIGN = {"camera": 0, "ground": 1, "dirX": 2, "dirY": 3, "dirZ": 4}
_SHAKE_TABLES = {"random": 0, "sineY": 1}
_ONE_OVER_255 = struct.unpack("<f", struct.pack("<f", 1.0 / 255.0))[0]


def _vector(items) -> WireVector:
    items = list(items)
    return WireVector(count=len(items), items=items, source_span=None)


_SWITCH_START = "-+"


def _is_switch(token: str) -> bool:
    return len(token) > 1 and token[0] in _SWITCH_START and token[1].isalpha()


class Args:
    """A command line, exposing the game's switch-parsing helpers."""

    def __init__(self, compiler: "FxCompiler", command: Command) -> None:
        self.c = compiler
        self.command = command
        self.argv: List[str] = [command.name] + list(command.args)

    def fail(self, message: str) -> "FxError":
        return FxError(message, file=self.c.current_file, line=self.command.line)

    def positional(self, minimum: int = 0) -> List[str]:
        out: List[str] = []
        for token in self.argv[1:]:
            if _is_switch(token):
                break
            out.append(token)
        if len(out) < minimum:
            raise self.fail(f"{self.command.name}: expecting at least {minimum} arguments")
        return out

    def switch(self, name: str, minimum: int = 0) -> Optional[List[str]]:
        for i, token in enumerate(self.argv):
            if token[:1] == "-" and token[1:] == name:
                self.argv[i] = "+" + name
                values: List[str] = []
                for value in self.argv[i + 1 :]:
                    if _is_switch(value):
                        break
                    values.append(value)
                if len(values) < minimum:
                    raise self.fail(f"-{name}: expecting at least {minimum} arguments")
                return values
        return None

    def check_handled(self) -> None:
        for token in self.argv[1:]:
            if len(token) > 1 and token[0] == "-" and token[1].isalpha():
                raise self.fail(f"Unexpected switch: {token}")

    def number(self, text: str) -> float:
        try:
            return f32(evaluate(text))
        except FxError as error:
            raise self.fail(error.message) from error

    def uint(self, text: str) -> int:
        try:
            result = evaluate(text)
        except FxError as error:
            raise self.fail(error.message) from error
        return max(0, min(0xFFFFFFFF, int(result)))

    def integer(self, text: str) -> int:
        # ParseInt rounds through the single-precision trick
        # `(int)((float)x + 12582912.0) - 0x4b400000`.
        return _bias_round(self.number(text))

    def ranged(self, text: str, low: float, high: float) -> float:
        value = self.number(text)
        if not low <= value <= high:
            raise self.fail(f"argument out of range: expecting [{low:g}..{high:g}], got {value:g}")
        return value

    def ranged_int(self, text: str, low: int, high: int) -> int:
        value = self.integer(text)
        if not low <= value <= high:
            raise self.fail(f"argument out of range: expecting [{low}..{high}], got {value}")
        return value

    def vec3(self, text: str) -> Vec3:
        parts = text.split()
        if len(parts) > 3:
            raise self.fail("Too many components for a Vector3")
        x = [self.number(p) for p in parts] + [0.0] * 3
        return Vec3(x[0], x[1], x[2])

    def vec2(self, text: str) -> Vec2:
        parts = text.split()
        if len(parts) > 2:
            raise self.fail("Too many components for a Vector2")
        x = [self.number(p) for p in parts] + [0.0] * 2
        return Vec2(x[0], x[1])

    def color(self, text: str) -> Vec3:
        parts = text.split()
        if len(parts) != 3:
            raise self.fail("Wrong number of color components")
        return Vec3(*(self.number(p) for p in parts))

    def float_range(self, values: List[str]) -> Vec2:
        """ParseFloatRange: `a [b]`, a single value stored at both ends."""

        first = self.number(values[0])
        return Vec2(first, self.number(values[1]) if len(values) > 1 else first)

    def enum(self, table: Dict[str, int], text: str) -> int:
        if text not in table:
            raise self.fail(f"Unknown enum '{text}'")
        return table[text]


def _set_bit(record, attribute: str, bit: int, value: bool = True) -> None:
    raw = getattr(record, attribute)
    current = raw.value | (1 << bit) if value else raw.value & ~(1 << bit)
    setattr(record, attribute, raw.replace(current))


def _set_f(record, attribute: str, value: float) -> None:
    setattr(record, attribute, make_raw_f32(f32(value)))


def _set_u32(record, attribute: str, value: int) -> None:
    setattr(record, attribute, make_raw_u32(value & 0xFFFFFFFF))


def _set_u8(record, attribute: str, value: int) -> None:
    setattr(record, attribute, make_raw_u8(value & 0xFF))


class _HashMultimap:
    """Replica of the SGI `__gnu_cxx::hash_multimap<string, int>` that orders
    the on-disk effect name map (hash `h = 5*h + c`, prime bucket growth).

    The file stores this container's iteration order, so reproducing that
    order takes the same data structure, and it has no other reason to
    exist. Checked against all 1154 vanilla entries (a generic insertion-order
    list reproduced none of the on-disk order).
    """

    _PRIMES = (53, 97, 193, 389, 769, 1543, 3079, 6151, 12289, 24593, 49157, 98317, 196613, 393241, 786433, 1572869, 3145739, 6291469, 12582917, 25165843, 50331653, 100663319, 201326611, 402653189, 805306457, 1610612741, 3221225473, 4294967291)

    def __init__(self) -> None:
        self.buckets: List[List[tuple]] = [[] for _ in range(self._next_prime(100))]
        self.count = 0

    @classmethod
    def _next_prime(cls, n: int) -> int:
        return next((p for p in cls._PRIMES if p >= n), cls._PRIMES[-1])

    @staticmethod
    def _hash(text: str) -> int:
        h = 0
        for byte in text.encode("latin-1", "replace"):
            h = (5 * h + byte) & 0xFFFFFFFF
        return h

    def insert_equal(self, name: str, target: int) -> None:
        if self.count + 1 > len(self.buckets):
            size = self._next_prime(self.count + 1)
            grown: List[List[tuple]] = [[] for _ in range(size)]
            for bucket in self.buckets:
                for item in bucket:
                    grown[self._hash(item[0]) % size].insert(0, item)
            self.buckets = grown
        chain = self.buckets[self._hash(name) % len(self.buckets)]
        for i, item in enumerate(chain):
            if item[0] == name:
                chain.insert(i + 1, (name, target))
                break
        else:
            chain.insert(0, (name, target))
        self.count += 1

    def items(self):
        return (item for bucket in self.buckets for item in bucket)


@dataclass
class _Macro:
    params: List[str]
    body: List[Command]


@dataclass
class _ParticleState:
    record: ParticleDescriptor
    name: str
    tractor_time: float = 0.0
    tractor_time_scale: float = 1.0


class FxCompiler:
    """Executes parsed `.fx` commands against a fresh resource."""

    def __init__(self, *, file: str = "") -> None:
        self.file = file
        self.current_file = file
        self.resource = default_resource()
        self.textures: Dict[str, int] = {}
        self.models: Dict[str, int] = {}
        self.sounds: Dict[str, int] = {}
        self.brushes: Dict[str, int] = {}
        self.particle_names: Dict[str, int] = {}
        self.dynamic_names: Dict[str, int] = {}
        self.decal_names: Dict[str, int] = {}
        self.shake_names: Dict[str, int] = {}
        self.light_names: Dict[str, int] = {}
        self.sequence_names: Dict[str, int] = {}
        self.effect_by_key: Dict[tuple, int] = {}
        self.effect_names: Dict[str, List[int]] = {}
        self.effect_vector_capacity = 0
        self.child_capacities: List[int] = []
        self.name_table = _HashMultimap()
        self.key_map: List[StringU32U32Record] = []
        self.triggers: List[MessageTrigger] = []
        self.remaps: Dict[str, tuple] = {}
        self.variables: Dict[str, str] = {}
        self.namespaces: List[str] = []
        self.macros: Dict[str, _Macro] = {}
        self.blocks: List[str] = []
        self.particle: Optional[_ParticleState] = None
        self.dynamic: Optional[DynamicParticleDescriptor] = None
        self.decal: Optional[DecalDescriptor] = None
        self.shake: Optional[ShakeDescriptor] = None
        self.light: Optional[LightDescriptor] = None
        self.sequence = None
        self.effect: Optional[EffectDescription] = None
        self.effect_group = 0
        self.select_group = 0
        self.select_counter = 0
        self.select_start = 0
        self.system_sequence = False
        self._active_macro_params: Optional[Dict[str, str]] = None

    # --- driving ----------------------------------------------------------

    def run(self, commands: List[Command]) -> None:
        for command in commands:
            self._execute(command)

    def finish(self) -> EffDirResource:
        resource = self.resource
        resource.effect_name_map = _vector(
            StringU32Pair(name=WireString.from_text(name), target=make_raw_u32(target)) for name, target in self.name_table.items()
        )
        resource.effect_key_map = _vector(self.key_map)
        resource.message_triggers = _vector(self.triggers)
        return resource

    def _execute(self, command: Command) -> None:
        self.current_file = command.file or self.file
        name = self._substitute(command.name, command.line)
        args = [self._substitute(a, command.line) for a in command.args]
        expanded = Command(name, args, command.line, command.body)
        if command.body is not None and name == "define":
            self._define(expanded)
            return
        handler = self._find_handler(name)
        if handler is None:
            raise FxError(f"Unknown command '{name}'", file=self.current_file, line=command.line)
        arguments = Args(self, expanded)
        handler(arguments)
        arguments.check_handled()

    def _find_handler(self, name: str) -> Optional[Callable[[Args], None]]:
        for kind in reversed(self.blocks):
            handler = _BLOCK_TABLES.get(kind, {}).get(name)
            if handler is not None:
                return lambda a: handler(self, a)
        handler = _TOP_LEVEL.get(name)
        return (lambda a: handler(self, a)) if handler is not None else None

    def _run_body(self, command: Command, kind: str) -> None:
        self.blocks.append(kind)
        try:
            for child in command.body or []:
                self._execute(child)
        finally:
            self.blocks.pop()

    # --- variables, namespaces, macros, eval --------------------------------

    def _lookup_variable(self, name: str) -> Optional[str]:
        for depth in range(len(self.namespaces), -1, -1):
            key = ":".join(self.namespaces[:depth] + [name])
            if key in self.variables:
                return self.variables[key]
        return None

    def _substitute(self, text: str, line: int) -> str:
        if "%" in text and self._active_macro_params is not None:
            text = self._substitute_params(text, line)
        if "$" not in text:
            return text
        out: List[str] = []
        i = 0
        while i < len(text):
            if text[i] != "$":
                out.append(text[i])
                i += 1
                continue
            j = i + 1
            braced = j < len(text) and text[j] == "{"
            if braced:
                j += 1
            start = j
            while j < len(text) and (text[j].isalnum() or text[j] in "_:"):
                j += 1
            value = self._lookup_variable(text[start:j])
            if value is None:
                raise FxError(f"Unknown variable: '{text[start:j]}'", file=self.current_file, line=line)
            out.append(value)
            if braced and j < len(text) and text[j] == "}":
                j += 1
            i = j
        return "".join(out)

    def _substitute_params(self, text: str, line: int) -> str:
        out: List[str] = []
        i = 0
        params = self._active_macro_params or {}
        while i < len(text):
            if text[i] != "%":
                out.append(text[i])
                i += 1
                continue
            j = i + 1
            braced = j < len(text) and text[j] == "{"
            if braced:
                j += 1
            start = j
            while j < len(text) and (text[j].isalnum() or text[j] == "_"):
                j += 1
            key = text[start:j]
            if key not in params:
                raise FxError(f"Unknown parameter: '{key}'", file=self.current_file, line=line)
            out.append(params[key])
            if braced and j < len(text) and text[j] == "}":
                j += 1
            i = j
        return "".join(out)

    def _define(self, command: Command) -> None:
        if not command.args:
            raise FxError("define: missing definition name", file=self.current_file, line=command.line)
        params = command.args[1].split() if len(command.args) > 1 else []
        self.macros[command.args[0]] = _Macro(params, command.body or [])

    def _create(self, a: Args) -> None:
        values = a.positional(1)
        macro = self.macros.get(values[0])
        if macro is None:
            raise a.fail(f"Unknown definition: '{values[0]}'")
        arguments = values[1].split() if len(values) > 1 else []
        if len(arguments) != len(macro.params):
            raise a.fail("Wrong number of arguments")
        self._instantiate(macro, dict(zip(macro.params, arguments)))

    def _array_create(self, a: Args) -> None:
        values = a.positional(2)
        macro = self.macros.get(values[0])
        if macro is None:
            raise a.fail(f"Unknown definition: '{values[0]}'")
        count = a.uint(values[1])
        for index in range(count):
            self._instantiate(macro, dict(zip(macro.params, [str(index), str(count)])))

    def _instantiate(self, macro: _Macro, parameters: Dict[str, str]) -> None:
        saved = self._active_macro_params
        self._active_macro_params = parameters
        try:
            for child in macro.body:
                self._execute(child)
        finally:
            self._active_macro_params = saved

    def _set_var(self, a: Args) -> None:
        values = a.positional(2)
        name, text = values[0], values[1]
        if a.command.name == "setf":
            text = _canonical_float(a.number(text))
        elif a.command.name == "seti":
            text = str(a.integer(text))
        elif a.command.name in ("setv3", "setc"):
            vector = a.color(text) if a.command.name == "setc" else a.vec3(text)
            scale = a.switch("scale", 1)
            multiply = a.switch("mult", 1)
            add = a.switch("add", 1)
            alpha = a.switch("alpha", 1)
            components = [vector.x, vector.y, vector.z]
            if scale:
                components = [f32(c * a.number(scale[0])) for c in components]
            if multiply:
                m = a.color(multiply[0]) if a.command.name == "setc" else a.vec3(multiply[0])
                components = [f32(c * o) for c, o in zip(components, (m.x, m.y, m.z))]
            if add:
                m = a.color(add[0]) if a.command.name == "setc" else a.vec3(add[0])
                components = [f32(c + o) for c, o in zip(components, (m.x, m.y, m.z))]
            if alpha:
                components.append(a.number(alpha[0]))
            text = " ".join(_canonical_float(c) for c in components)
        self.variables[":".join(self.namespaces + [name])] = text

    def _namespace(self, a: Args) -> None:
        values = a.positional(1)
        self.namespaces.append(values[0])
        try:
            self._run_body(a.command, "namespace")
        finally:
            self.namespaces.pop()

    def _eval(self, a: Args) -> None:
        values = a.positional(1)
        if len(values) != 1:
            raise a.fail("eval takes exactly one string argument")
        commands = parse_file(values[0] + "\n", file=self.current_file)
        if len(commands) != 1:
            raise a.fail("eval expects exactly one command")
        commands[0].line = a.command.line
        self._execute(commands[0])

    # --- ID maps and top-level bindings ------------------------------------

    def _id_map(self, a: Args, table: Dict[str, int]) -> None:
        if len(a.command.args) != 2:
            raise a.fail("Wrong number of arguments")
        table[a.command.args[0].lower()] = a.uint(a.command.args[1])

    def _effect_id(self, a: Args) -> None:
        if len(a.command.args) != 3:
            raise a.fail("Wrong number of arguments")
        self.key_map.append(self._key_record(a.command.args[2], a.uint(a.command.args[0]), a.uint(a.command.args[1])))

    def _effect_group_block(self, a: Args) -> None:
        if not a.command.args:
            raise a.fail("No ID specified!")
        self.effect_group = a.uint(a.command.args[0])
        self._run_body(a.command, "effectGroup")

    def _effect_instance(self, a: Args) -> None:
        if len(a.command.args) != 2:
            raise a.fail("Wrong number of arguments")
        self.key_map.append(self._key_record(a.command.args[1], self.effect_group, a.uint(a.command.args[0])))

    @staticmethod
    def _key_record(name: str, group: int, instance: int) -> StringU32U32Record:
        return StringU32U32Record(name=WireString.from_text(name.lower()), group_id=make_raw_u32(group), instance_id=make_raw_u32(instance))

    def _message_trigger(self, a: Args) -> None:
        values = a.positional(2)
        self.triggers.append(MessageTrigger(message_id=make_raw_u32(a.uint(values[0])), effect_name=WireString.from_text(values[1])))

    def _camera(self, a: Args) -> None:
        values = a.positional(1)
        zooms = [a.number(v) for v in values]
        if len(zooms) == 1:
            for _ in range(4):
                zooms.append(f32(zooms[-1] * 0.5))
        parallax = a.switch("parallax", 2)
        base, top = (a.number(parallax[0]), a.number(parallax[1])) if parallax else (100.0, 101.0)
        size = a.switch("size", 1)
        side_swipe = a.switch("sideSwipe", 1)
        # `(int)(far - near)`, clamped at zero: the game stores an integer range.
        span = max(0, int(top - base))
        stored = zooms + [base, float(span), a.number(size[0]) if size else 4.0, a.number(side_swipe[0]) if side_swipe else 7.0]
        self.resource.trailing_float_metadata = TrailingFloatMetadata(
            present=make_raw_u8(1), marker=make_raw_u16(0), count=make_raw_u32(len(zooms)), values=tuple(stored)
        )

    # --- definition blocks ---------------------------------------------------

    def _base_name(self, a: Args) -> Optional[str]:
        values = a.argv[2:] if len(a.argv) > 2 else []
        if len(values) >= 1 and values[0] != ":":
            raise a.fail("Expecting ':'")
        return values[1] if len(values) >= 2 else None

    def _particles_block(self, a: Args) -> None:
        name = a.positional(1)[0]
        record = default_particle()
        base = self._base_name(a)
        if base is not None:
            record = copy.deepcopy(self._lookup(self.particle_names, self.resource.particles.items, base, a, "Unknown particle definition: %s"))
        tractor_time = record.tractor_points.items[-1].amount.value if record.tractor_points.items else 0.0
        self.particle = _ParticleState(record, name, tractor_time, 1.0)
        self._run_body(a.command, "particles")
        self.resource.particles = self._store(self.particle_names, self.resource.particles, name, self.particle.record)
        self.particle = None

    def _dynamic_block(self, a: Args) -> None:
        name = a.positional(1)[0]
        self.dynamic = default_dynamic_particle()
        base = self._base_name(a)
        if base is not None:
            self.dynamic = copy.deepcopy(self._lookup(self.dynamic_names, self.resource.dynamic_particles.items, base, a, "Unknown particle definition: %s"))
        self._run_body(a.command, "dynamicParticle")
        self.resource.dynamic_particles = self._store(self.dynamic_names, self.resource.dynamic_particles, name, self.dynamic)
        self.dynamic = None

    def _decal_block(self, a: Args) -> None:
        name = a.positional(1)[0]
        self.decal = default_decal()
        base = self._base_name(a)
        if base is not None:
            self.decal = copy.deepcopy(self._lookup(self.decal_names, self.resource.decals.items, base, a, "Unknown particle definition: %s"))
        self._run_body(a.command, "decal")
        self.resource.decals = self._store(self.decal_names, self.resource.decals, name, self.decal)
        self.decal = None

    def _shake_block(self, a: Args) -> None:
        name = a.positional(1)[0]
        self.shake = default_shake()
        self.shake.length = make_raw_f32(5.0)
        self.shake.fade = make_raw_f32(1.0)
        self.shake.aspect = make_raw_f32(1.0)
        self.shake.amplitude = _vector([1.0])
        self.shake.frequency = _vector([60.0])
        base = self._base_name(a)
        if base is not None:
            self.shake = copy.deepcopy(self._lookup(self.shake_names, self.resource.shakes.items, base, a, "Unknown shake definition: %s"))
        self._run_body(a.command, "shake")
        self.resource.shakes = self._store(self.shake_names, self.resource.shakes, name, self.shake)
        self.shake = None

    def _light_block(self, a: Args) -> None:
        name = a.positional(1)[0]
        self.light = default_light()
        values = a.positional()
        if len(values) > 1:
            if values[1] != ":":
                raise a.fail("Expecting ':'")
            if len(values) > 2:
                self.light = copy.deepcopy(self._lookup(self.light_names, self.resource.lights.items, values[2], a, "Unknown light definition: %s"))
        self._run_body(a.command, "light")
        if not self.light.strength.items:
            self.light.strength = _vector([1.0])
        if not self.light.color.items:
            # `nS3D::kColorBlue` in the end-of-block fallback (Mac 0x00788BC0)
            self.light.color = _vector([Vec3(0.0, 0.0, 1.0)])
        self.resource.lights = self._store(self.light_names, self.resource.lights, name, self.light)
        self.light = None

    def _sequence_block(self, a: Args) -> None:
        name = a.positional(1)[0]
        self.sequence = default_sequence()
        if a.switch("loop") is not None:
            _set_bit(self.sequence, "flags", 0)
        if a.switch("noOverlap") is not None:
            _set_bit(self.sequence, "flags", 1)
        if a.switch("hardStart") is not None:
            _set_bit(self.sequence, "flags", 2)
        self._run_body(a.command, "sequence")
        components = self.resource.components
        components.sequences = self._store(self.sequence_names, components.sequences, name, self.sequence)
        self.sequence = None

    @staticmethod
    def _lookup(names: Dict[str, int], items: List, name: str, a: Args, message: str):
        index = names.get(name.lower())
        if index is None:
            raise a.fail(message % name)
        return items[index]

    @staticmethod
    def _store(names: Dict[str, int], vector: WireVector, name: str, record) -> WireVector:
        """`Add*Description`: lowercased name, append or replace in place."""

        key = name.lower()
        if key in names:
            vector.items[names[key]] = record
            return vector
        names[key] = len(vector.items)
        return _vector(vector.items + [record])

    # --- particle sub-commands ------------------------------------------------

    def _p_curve(self, a: Args, attribute: str, scale: float = 1.0) -> None:
        p = self.particle.record
        setattr(p, attribute, _vector(f32(a.number(v) * scale) for v in a.positional(1)))

    def _p_alpha(self, a: Args) -> None:
        p = self.particle.record
        self._p_curve(a, "alpha_curve")
        vary = a.switch("vary", 1)
        if vary:
            _set_f(p, "alpha_vary", a.ranged(vary[0], 0.0, 1.0))
        if a.command.name.endswith("255"):
            p.alpha_curve = _vector(f32(v * _ONE_OVER_255) for v in p.alpha_curve.items)

    def _p_color(self, a: Args) -> None:
        p = self.particle.record
        p.color_curve = _vector(a.color(v) for v in a.positional(1))
        vary = a.switch("vary", 1)
        if vary:
            v = a.vec3(vary[0])
            if not all(0.0 <= c <= 1.0 for c in (v.x, v.y, v.z)):
                raise a.fail("argument out of range: expecting components [0..1]")
            p.color_vary = v
        if a.command.name.endswith("255"):
            p.color_curve = _vector(Vec3(f32(c.x * _ONE_OVER_255), f32(c.y * _ONE_OVER_255), f32(c.z * _ONE_OVER_255)) for c in p.color_curve.items)

    def _p_size(self, a: Args) -> None:
        p = self.particle.record
        self._p_curve(a, "size_curve", 50.0)
        vary = a.switch("vary", 1)
        if vary:
            _set_f(p, "size_vary", a.ranged(vary[0], 0.0, 1.0))

    def _p_aspect(self, a: Args) -> None:
        p = self.particle.record
        self._p_curve(a, "aspect_curve")
        vary = a.switch("vary", 1)
        if vary:
            _set_f(p, "aspect_vary", a.ranged(vary[0], 0.0, 1.0))

    def _p_rotate(self, a: Args) -> None:
        p = self.particle.record
        self._p_curve(a, "rotate_curve")
        vary = a.switch("vary", 1)
        if vary:
            _set_f(p, "rotate_vary", a.ranged(vary[0], 0.0, 1.0))
        offset = a.switch("offset", 1)
        if offset:
            _set_f(p, "rotate_offset", a.number(offset[0]))

    def _p_life(self, a: Args) -> None:
        p = self.particle.record
        values = a.positional(1)
        base = a.number(values[0])
        vary = a.number(values[1]) if len(values) > 1 else 0.0
        p.life = Vec2(f32(base - vary), f32(base + vary))
        preroll = a.switch("preroll", 1)
        _set_f(p, "preroll", a.number(preroll[0]) if preroll else base)

    def _p_stretch(self, a: Args) -> None:
        if len(a.argv) < 2:
            raise a.fail("Not enough arguments")
        _set_f(self.particle.record, "stretch", a.number(a.argv[1]))

    def _p_rate_shared(self, a: Args, p: ParticleDescriptor) -> None:
        """ParseRateCurveCommands: the timing switches `rate`/`inject` share
        with `emit`."""

        loop = a.switch("loop", 1)
        if loop:
            _set_f(p, "emit_loop_interval", a.number(loop[0]))
            if len(loop) > 1:
                _set_u32(p, "emit_loop_count", a.uint(loop[1]))
        single = a.switch("single")
        if single is not None:
            _set_f(p, "emit_loop_interval", a.number(single[0]) if single else 0.001)
            _set_u32(p, "emit_loop_count", 1)
        if a.switch("sustain") is not None:
            _set_bit(p, "flags_0", 3)
        if a.switch("scale") is not None:
            _set_bit(p, "flags_0", 19)
        if a.switch("areaScale") is not None:
            _set_bit(p, "flags_0", 20)
        if a.switch("volumeScale") is not None:
            _set_bit(p, "flags_0", 21)
        delay = a.switch("delay", 1)
        if delay:
            p.emit_delay = a.float_range(delay)
        trigger = a.switch("trigger", 1) or a.switch("retrigger", 1)
        if trigger:
            p.emit_trigger = a.float_range(trigger)

    def _p_rate(self, a: Args) -> None:
        p = self.particle.record
        inject = a.switch("inject", 1)
        if inject:
            p.emit_curve = _vector([a.number(inject[0])])
            _set_bit(p, "flags_0", 1)
        else:
            p.emit_curve = _vector(a.number(v) for v in a.positional(1))
        self._p_rate_shared(a, p)

    def _p_inject(self, a: Args) -> None:
        p = self.particle.record
        p.emit_curve = _vector([a.number(a.positional(1)[0])])
        _set_bit(p, "flags_0", 1)
        self._p_rate_shared(a, p)

    def _p_maintain(self, a: Args) -> None:
        p = self.particle.record
        p.emit_curve = _vector([a.number(a.positional(1)[0])])
        _set_bit(p, "flags_0", 2)
        delay = a.switch("delay", 1)
        if delay:
            p.emit_delay = a.float_range(delay)

    def _p_emit(self, a: Args) -> None:
        p = self.particle.record
        inject = a.switch("inject", 1)
        if inject:
            p.emit_curve = _vector([a.number(inject[0])])
            _set_bit(p, "flags_0", 1)
        else:
            rate = a.switch("rate", 1)
            if rate:
                p.emit_curve = _vector(a.number(v) for v in rate)
        self._p_rate_shared(a, p)
        velocity = a.switch("velocity", 1)
        if velocity:
            speed = a.number(velocity[1]) if len(velocity) > 1 else 1.0
            vary = a.number(velocity[2]) if len(velocity) > 2 else 0.0
            direction = _normalized(a.vec3(velocity[0]), "yzx")
            p.emit_velocity_bounds = _cube(direction, vary)
            p.emit_speed = Vec2(f32(speed * f32(1.0 - vary)), f32(speed * f32(1.0 + vary)))
        speed_switch = a.switch("speed", 1)
        if speed_switch:
            base = a.number(speed_switch[0])
            vary = a.number(speed_switch[1]) if len(speed_switch) > 1 else 0.0
            p.emit_speed = Vec2(f32(base - vary), f32(base + vary))
        direction_switch = a.switch("dir", 1)
        if direction_switch:
            direction = a.vec3(direction_switch[0])
            if direction.x * direction.x + direction.y * direction.y + direction.z * direction.z > 0.0:
                direction = _normalized(direction, "zyx")
            vary = Vec3(0.0, 0.0, 0.0)
            if len(direction_switch) > 1:
                parts = direction_switch[1].split()
                if len(parts) == 1:
                    v = a.number(parts[0])
                    vary = Vec3(v, v, v)
                elif len(parts) == 3:
                    vary = Vec3(*(a.number(q) for q in parts))
                else:
                    raise a.fail("Expecting float or vector3 for second -dir argument")
            p.emit_velocity_bounds = Bounds3(
                Vec3(f32(direction.x - vary.x), f32(direction.y - vary.y), f32(direction.z - vary.z)),
                Vec3(f32(direction.x + vary.x), f32(direction.y + vary.y), f32(direction.z + vary.z)),
            )
        vel = a.switch("vel", 1)
        if vel:
            value = a.vec3(vel[0])
            magnitude_squared = value.x * value.x + value.y * value.y + value.z * value.z
            magnitude = f32(math.sqrt(magnitude_squared)) if magnitude_squared > 0.0 else 0.0
            if magnitude:
                value = Vec3(f32(value.x / magnitude), f32(value.y / magnitude), f32(value.z / magnitude))
            p.emit_speed = Vec2(magnitude, magnitude)
            p.emit_velocity_bounds = Bounds3(value, value)
        if a.switch("base") is not None:
            _set_bit(p, "flags_0", 5)

    def _p_source(self, a: Args) -> None:
        p = self.particle.record
        minimum = Vec3(-1.0, 0.0, -1.0)
        maximum = Vec3(1.0, 0.0, 1.0)
        translate: Optional[str] = None
        point = a.switch("point")
        square = a.switch("square", 1) if point is None else None
        quad = a.switch("quad", 1) if point is None and square is None else None
        cube = a.switch("cube", 1) if point is None and square is None and quad is None else None
        box = a.switch("box", 1) if point is None and square is None and quad is None and cube is None else None
        none_shape = point is None and square is None and quad is None and cube is None and box is None
        if point is not None:
            minimum = maximum = Vec3(0.0, 0.0, 0.0)
            translate = point[0] if point else None
        elif square is not None:
            s = a.number(square[0])
            minimum, maximum = Vec3(-s, -0.0, -s), Vec3(s, 0.0, s)
            translate = square[1] if len(square) > 1 else None
        elif quad is not None:
            q = a.vec2(quad[0])
            minimum, maximum = Vec3(-q.x, -0.0, -q.y), Vec3(q.x, 0.0, q.y)
            translate = quad[1] if len(quad) > 1 else None
        elif cube is not None:
            s = a.number(cube[0])
            minimum, maximum = Vec3(-s, -s, -s), Vec3(s, s, s)
            translate = cube[1] if len(cube) > 1 else None
        elif box is not None:
            v = a.vec3(box[0])
            minimum, maximum = Vec3(-v.x, -v.y, -v.z), v
            translate = box[1] if len(box) > 1 else None
        elif none_shape:
            dice = a.switch("dice", 1)
            if dice:
                _set_f(p, "model_speed", a.number(dice[0]))
                minimum = maximum = Vec3(0.0, 0.0, 0.0)
            elif a.switch("model") is not None:
                _set_bit(p, "flags_0", 6)
            elif a.switch("modelBase") is not None:
                _set_bit(p, "flags_0", 7)
            else:
                city = a.switch("city")
                windy = a.switch("cityWindySide") if city is None else None
                if city is not None or windy is not None:
                    _set_bit(p, "flags_0", 12)
                    if windy is not None:
                        _set_bit(p, "flags_0", 13)
                    limits = city if city is not None else windy
                    if limits:
                        low = a.number(limits[0])
                        high = a.number(limits[1]) if len(limits) > 1 else low
                        minimum = Vec3(minimum.x, low, minimum.z)
                        maximum = Vec3(maximum.x, high, maximum.z)
        if translate is not None:
            t = a.vec3(translate)
            minimum = Vec3(f32(minimum.x + t.x), f32(minimum.y + t.y), f32(minimum.z + t.z))
            maximum = Vec3(f32(maximum.x + t.x), f32(maximum.y + t.y), f32(maximum.z + t.z))
        p.source_bounds = Bounds3(minimum, maximum)
        if a.switch("scaleParticles") is not None:
            _set_bit(p, "flags_0", 22)
        if a.switch("pinToTerrain") is not None:
            _set_bit(p, "flags_0", 14)
        if a.switch("pinToWater") is not None:
            _set_bit(p, "flags_0", 15)
        if a.switch("terrainOnly") is not None:
            _set_bit(p, "flags_0", 16)
            p.height_range = Vec2(0.0, p.height_range.y)
        if a.switch("waterOnly") is not None:
            _set_bit(p, "flags_0", 16)
            p.height_range = Vec2(p.height_range.x, 0.0)
        if a.switch("seaOnly") is not None:
            _set_bit(p, "flags_0", 16)
            p.height_range = Vec2(p.height_range.x, 0.0)
            _set_bit(p, "flags_0", 17)
        if a.switch("lakeOnly") is not None:
            _set_bit(p, "flags_0", 16)
            p.height_range = Vec2(p.height_range.x, 0.0)
            _set_bit(p, "flags_0", 18)
        below = a.switch("belowHeight", 1)
        if below:
            _set_bit(p, "flags_0", 16)
            p.height_range = Vec2(p.height_range.x, a.number(below[0]))
        above = a.switch("aboveHeight", 1)
        if above:
            _set_bit(p, "flags_0", 16)
            p.height_range = Vec2(a.number(above[0]), p.height_range.y)
        height = a.switch("heightRange", 2)
        if height:
            _set_bit(p, "flags_0", 16)
            p.height_range = Vec2(a.number(height[0]), a.number(height[1]))
        if a.switch("killOutsideCity") is not None:
            _set_bit(p, "flags_0", 11)
        if a.switch("resetIncoming") is not None:
            _set_bit(p, "flags_2", 9)

    def _p_force(self, a: Args) -> None:
        state = self.particle
        p = state.record
        if a.switch("reset") is not None:
            p.force = Vec3(0.0, 0.0, 0.0)
            p.tractor_points = _vector([])
        gravity = a.switch("gravity", 1)
        if gravity:
            g = a.number(gravity[0])
            p.force = Vec3(f32(p.force.x + 0.0), f32(p.force.y - g), f32(p.force.z + 0.0))
        wind = a.switch("wind", 1)
        if wind:
            direction = _normalized(a.vec3(wind[0]), "zyx")
            if len(wind) > 1:
                magnitude = a.number(wind[1])
                direction = Vec3(f32(magnitude * direction.x), f32(magnitude * direction.y), f32(magnitude * direction.z))
            p.force = Vec3(f32(p.force.x + direction.x), f32(p.force.y + direction.y), f32(p.force.z + direction.z))
        global_wind = a.switch("global_wind", 1)
        if global_wind:
            _set_f(p, "global_wind", a.number(global_wind[0]))
        screw = a.switch("screw", 1)
        if screw:
            _set_f(p, "screw", f32(a.number(screw[0]) * 0.02))
        bomb = a.switch("bomb", 1)
        if bomb:
            _set_f(p, "bomb", a.number(bomb[0]))
            if len(bomb) > 1:
                p.bomb_direction = a.vec3(bomb[1])
        drag = a.switch("drag", 1)
        if drag:
            _set_f(p, "drag", a.number(drag[0]))
        duck = a.switch("motherDuck", 1)
        attractor = a.switch("attractor", 1) if duck is None else None
        alpha_attractor = a.switch("alphaAttractor", 1) if duck is None and attractor is None else None
        automata = a.switch("automata", 2) if duck is None and attractor is None and alpha_attractor is None else None
        if duck is not None or attractor is not None or alpha_attractor is not None:
            values = duck or attractor or alpha_attractor
            _set_f(p, "attractor_strength", a.number(values[0]))
            p.attractor_curve = _vector(a.number(v) for v in values[1:])
            if duck is not None:
                _set_bit(p, "flags_0", 27)
            if alpha_attractor is not None:
                _set_bit(p, "flags_0", 26)
                _set_bit(p, "flags_2", 4)
        if automata is not None and (not p.attractor_curve.items or p.automata_id.value != 0):
            _set_f(p, "attractor_strength", 1.0)
            _set_u32(p, "automata_id", a.uint(automata[0]))
            p.attractor_curve = _vector([a.number(automata[1])])
        tractor_relative = a.switch("tractorRel", 2)
        tractor = tractor_relative if tractor_relative is not None else a.switch("tractor", 2)
        if tractor is not None:
            self._p_tractor(a, state, tractor, tractor_relative is not None)
        reset_speed = a.switch("tractorResetSpeed", 1)
        if reset_speed:
            _set_f(p, "tractor_reset_speed", a.number(reset_speed[0]))
        time_scale = a.switch("tractorTimeScale", 1)
        if time_scale:
            factor = a.number(time_scale[0])
            state.tractor_time_scale = factor
            state.tractor_time = f32(factor * state.tractor_time)
            p.life = Vec2(f32(factor * p.life.x), f32(factor * p.life.y))
            rescaled = []
            for point in p.tractor_points.items:
                rescaled.append(
                    TractorPoint(
                        position=point.position,
                        direction=Vec3(f32(point.direction.x / factor), f32(point.direction.y / factor), f32(point.direction.z / factor)),
                        time=make_raw_f32(f32(factor * point.time.value)),
                        amount=make_raw_f32(f32(factor * point.amount.value)),
                    )
                )
            p.tractor_points = _vector(rescaled)
        terrain = a.switch("terrainRepel", 2)
        if terrain:
            p.terrain_repel = Vec2(a.number(terrain[0]), a.number(terrain[1]))
            _set_bit(p, "flags_0", 10)
            if len(terrain) > 2:
                _set_f(p, "scout", a.number(terrain[2]))
            if len(terrain) > 3:
                _set_f(p, "vertical", a.number(terrain[3]))
            if len(terrain) > 4:
                _set_f(p, "kill_height", a.number(terrain[4]))
        explosion = a.switch("explosion", 2)
        if explosion:
            _set_f(p, "explosion", a.number(explosion[0]))
            p.explosion_curve = _vector(a.number(v) for v in explosion[1:])
        explosion_front = a.switch("explosionFront", 2)
        if explosion_front:
            _set_f(p, "explosion_front", a.number(explosion_front[0]))
            _set_f(p, "explosion_front_secondary", a.number(explosion_front[1]))

    def _p_tractor(self, a: Args, state: _ParticleState, values: List[str], relative: bool) -> None:
        p = state.record
        position = a.vec3(values[0])
        time_scale = state.tractor_time_scale
        points = p.tractor_points.items
        if len(values[1].split()) == 1:
            length = a.number(values[1])
            if points:
                anchor = points[-1].position
            else:
                bounds = p.source_bounds
                anchor = Vec3(f32((bounds.minimum.x + bounds.maximum.x) * 0.5), f32((bounds.minimum.y + bounds.maximum.y) * 0.5), f32((bounds.minimum.z + bounds.maximum.z) * 0.5))
            tangent = Vec3(f32(position.x - anchor.x), f32(position.y - anchor.y), f32(position.z - anchor.z))
            scale = f32(length / time_scale)
            squared = tangent.x * tangent.x + tangent.y * tangent.y + tangent.z * tangent.z
            if squared > 0.0:
                ratio = f32(scale / f32(math.sqrt(squared)))
                tangent = Vec3(f32(tangent.x * ratio), f32(tangent.y * ratio), f32(tangent.z * ratio))
        else:
            explicit = a.vec3(values[1])
            tangent = Vec3(f32(explicit.x / time_scale), f32(explicit.y / time_scale), f32(explicit.z / time_scale))
        if relative and points:
            last = points[-1].position
            position = Vec3(f32(position.x + last.x), f32(position.y + last.y), f32(position.z + last.z))
        start = state.tractor_time
        end = start
        if len(values) > 2:
            end = f32(f32(a.number(values[2]) * time_scale) + start)
            state.tractor_time = end
        point = TractorPoint(position=position, direction=tangent, time=make_raw_f32(start), amount=make_raw_f32(end))
        p.tractor_points = _vector(points + [point])
        _set_bit(p, "flags_0", 28)

    def _p_warp(self, a: Args) -> None:
        p = self.particle.record
        screw = a.switch("screw", 1)
        if screw:
            _set_f(p, "screw", f32(a.number(screw[0]) * 0.02))
        wiggle = a.switch("wiggle", 4)
        if wiggle:
            period = a.number(wiggle[0])
            strength = a.number(wiggle[1])
            radius = a.number(wiggle[2])
            phase = a.ranged(wiggle[3], 0.0, 1.0)
            angle = f32(phase * f32(2.0 * math.pi))
            direction = Vec3(0.0, period, 0.0)
            uv = Vec3(f32(f32(math.cos(angle)) * radius), 0.0, f32(-radius * f32(math.sin(angle))))
            p.wiggles = _vector(p.wiggles.items + [Wiggle(amount=make_raw_f32(strength), direction=direction, uv=uv)])
        wiggle_dir = a.switch("wiggleDir", 2)
        if wiggle_dir:
            amount = a.number(wiggle_dir[0])
            uv = a.vec3(wiggle_dir[1])
            second = a.vec3(wiggle_dir[2]) if len(wiggle_dir) > 2 else Vec3(0.0, 0.0, 0.0)
            p.wiggles = _vector(p.wiggles.items + [Wiggle(amount=make_raw_f32(amount), direction=second, uv=uv)])
        if a.switch("wiggleVerts") is not None:
            _set_bit(p, "flags_2", 8)
        uv_switch = a.switch("uv", 1)
        if uv_switch:
            _set_f(p, "uv_scale", a.number(uv_switch[0]))
            p.uv_range = a.vec2(uv_switch[1])
            _set_bit(p, "flags_2", 8)
        alpha = a.switch("alpha", 2)
        if alpha:
            p.alpha_warp_direction = _normalized(a.vec3(alpha[0]), "xyz")
            p.alpha_warp_curve = _vector(a.ranged(v, 0.0, 1.0) for v in alpha[1:])
            _set_bit(p, "flags_2", 8)

    def _p_random_walk(self, a: Args) -> None:
        p = self.particle.record
        _set_bit(p, "flags_0", 23)
        delay = a.switch("delay", 1)
        if delay:
            base = a.number(delay[0])
            vary = a.number(delay[1]) if len(delay) > 1 else 0.0
            p.random_walk_delay = Vec2(f32(base - vary), f32(base + vary))
        strength = a.switch("strength", 1)
        if strength:
            base = a.number(strength[0])
            vary = a.number(strength[1]) if len(strength) > 1 else 0.0
            p.random_walk_strength = Vec2(f32(base - vary), f32(base + vary))
        turn = a.switch("turn", 1)
        if turn:
            p.random_walk_turn = Vec2(a.ranged(turn[0], 0.0, 1.0), a.ranged(turn[1], 0.0, 1.0) if len(turn) > 1 else 0.0)
        if a.switch("wait") is not None:
            _set_bit(p, "flags_0", 24)
        if a.switch("preferSea") is not None:
            _set_bit(p, "flags_0", 25)
        prefer = a.switch("preferDir", 1)
        if prefer:
            p.prefer_direction = a.vec3(prefer[0])

    def _p_terrain_repel(self, a: Args) -> None:
        p = self.particle.record
        _set_bit(p, "flags_0", 10)
        values = a.positional(2)
        p.terrain_repel = Vec2(a.number(values[0]), a.number(values[1]))
        for name, attribute in (("scout", "scout"), ("vertical", "vertical"), ("killHeight", "kill_height")):
            value = a.switch(name, 1)
            if value:
                _set_f(p, attribute, a.number(value[0]))

    def _p_collide(self, a: Args) -> None:
        p = self.particle.record
        _set_bit(p, "flags_0", 8)
        bounce = a.switch("bounce", 1)
        if bounce:
            _set_f(p, "bounce", a.number(bounce[0]))
        elif p.bounce.value == 0.0:
            _set_f(p, "bounce", 0.3)
        if a.switch("sticky") is not None:
            _set_bit(p, "flags_0", 9)
        if a.switch("killOutsideCity") is not None:
            _set_bit(p, "flags_0", 11)
        effect = a.switch("effect", 1)
        if effect:
            _set_f(p, "collision_effect_or_death", a.number(effect[0]))
        death = a.switch("death", 1)
        if death:
            _set_f(p, "collision_effect_or_death", a.ranged(death[0], 0.0, 1.0))
        water = a.switch("deathByWater", 1)
        if water:
            _set_f(p, "death_by_water", a.ranged(water[0], 0.0, 1.0))
        if a.switch("destroyBuildings") is not None:
            _set_bit(p, "flags_1", 0)

    def _p_draw(self, a: Args, p: ParticleDescriptor) -> None:
        draw = a.switch("draw", 1)
        if draw:
            _set_u8(p, "draw_mode", a.enum(_PARTICLE_DRAW, draw[0]))
        if a.switch("light") is not None:
            _set_bit(p, "flags_0", 0)
        if a.switch("noCull") is not None:
            _set_bit(p, "flags_0", 4)
        sort = a.switch("sortOffset", 1)
        if sort:
            _set_f(p, "sort_offset", a.number(sort[0]))

    def _p_texture(self, a: Args) -> None:
        p = self.particle.record
        self._p_draw(a, p)
        if a.switch("vflip") is not None:
            _set_bit(p, "flags_0", 30)
        if a.switch("hflip") is not None:
            _set_bit(p, "flags_0", 29)
        values = a.positional(0 if p.resource_key.value else 1)
        if values:
            key = self.textures.get(values[0].lower())
            if key is None:
                raise a.fail(f"No such texture: '{values[0]}'")
            _set_u32(p, "resource_key", key)

    def _p_model(self, a: Args) -> None:
        p = self.particle.record
        _set_bit(p, "flags_2", 0)
        _set_u8(p, "draw_mode", 3)
        self._p_draw(a, p)
        for switch, bit_ in (("fakePerspective", 1), ("moveEntireSlave", 3), ("sustain", 5), ("applyLighting", 2), ("noCullFaces", 10)):
            if a.switch(switch) is not None:
                _set_bit(p, "flags_2", bit_)
        if a.switch("slaveApplyAlpha") is not None or a.switch("applyAlpha") is not None:
            _set_bit(p, "flags_2", 4)
        speed = a.switch("modelSpeed", 1)
        if speed:
            _set_f(p, "model_speed_static", a.number(speed[0]))
            _set_bit(p, "flags_2", 6)
        speed_static = a.switch("modelSpeedStatic", 1)
        if speed_static:
            _set_f(p, "model_speed_static", a.number(speed_static[0]))
        names = a.positional()
        if names:
            keys = []
            for name in names:
                key = self.models.get(name.lower())
                if key is None:
                    raise a.fail(f"No such model: '{name}'")
                keys.append(key)
            if len(keys) == 1:
                _set_u32(p, "resource_key", keys[0])
                p.model_keys = _vector([])
            else:
                p.model_keys = _vector(keys)

    def _p_align(self, a: Args) -> None:
        p = self.particle.record
        if len(a.argv) < 2:
            raise a.fail("Not enough arguments")
        _set_u8(p, "alignment_mode", a.enum(_ALIGN, a.argv[1]))
        damp = a.switch("damp", 1)
        if damp:
            _set_f(p, "alignment_damp", a.number(damp[0]))
        bank = a.switch("bank", 2)
        wind_bank = a.switch("windBank", 2) if bank is None else None
        if bank or wind_bank:
            values = bank or wind_bank
            p.bank_range = Vec2(a.number(values[0]), a.number(values[1]))
        if wind_bank:
            _set_bit(p, "flags_2", 7)

    def _p_effect_base(self, a: Args) -> None:
        self.particle.record.terrain_name = WireString.from_text(a.positional(1)[0])

    def _p_timed_effect(self, a: Args) -> None:
        p = self.particle.record
        _set_bit(p, "flags_0", 31)
        values = a.positional(2)
        entry = TimedEffect(effect_name=WireString.from_text(values[0]), time=make_raw_f32(a.number(values[1])))
        items = list(p.timed_effects.items)
        index = next((i for i, existing in enumerate(items) if entry.time.value < existing.time.value), len(items))
        items.insert(index, entry)
        p.timed_effects = _vector(items)

    def _p_zoom(self, a: Args) -> None:
        if len(a.argv) < 2:
            raise a.fail("Not enough arguments")
        a.uint(a.argv[1])

    # --- decal sub-commands ---------------------------------------------------

    def _d_curve(self, a: Args, attribute: str) -> None:
        setattr(self.decal, attribute, _vector(a.number(v) for v in a.positional(1)))

    def _d_alpha(self, a: Args) -> None:
        d = self.decal
        self._d_curve(a, "alpha")
        vary = a.switch("vary", 1)
        if vary:
            _set_f(d, "alpha_vary", a.ranged(vary[0], 0.0, 1.0))
        if a.command.name.endswith("255"):
            d.alpha = _vector(f32(v * _ONE_OVER_255) for v in d.alpha.items)

    def _d_color(self, a: Args) -> None:
        d = self.decal
        d.color = _vector(a.color(v) for v in a.positional(1))
        if a.command.name.endswith("255"):
            d.color = _vector(Vec3(f32(c.x * _ONE_OVER_255), f32(c.y * _ONE_OVER_255), f32(c.z * _ONE_OVER_255)) for c in d.color.items)

    def _d_size(self, a: Args) -> None:
        d = self.decal
        self._d_curve(a, "size")
        vary = a.switch("vary", 1)
        if vary:
            _set_f(d, "size_vary", a.ranged(vary[0], 0.0, 1.0))
        if a.switch("cityScale") is not None:
            _set_bit(d, "flags", 4)

    def _d_aspect(self, a: Args) -> None:
        self._d_curve(a, "aspect")

    def _d_rotate(self, a: Args) -> None:
        d = self.decal
        self._d_curve(a, "rotation")
        vary = a.switch("vary", 1)
        if vary:
            _set_f(d, "rotate_vary", a.ranged(vary[0], 0.0, 1.0))

    def _d_life(self, a: Args) -> None:
        d = self.decal
        values = a.positional()
        if values:
            _set_f(d, "life", a.number(values[0]))
        if a.switch("static") is not None:
            _set_bit(d, "flags", 6)
            _set_u8(d, "repeat_mode", 1)
        if a.switch("loop") is not None:
            _set_u8(d, "repeat_mode", 1)
        if a.switch("single") is not None:
            _set_u8(d, "repeat_mode", 2)
        if a.switch("sustain") is not None:
            _set_u8(d, "repeat_mode", 3)

    def _d_texture(self, a: Args) -> None:
        d = self.decal
        draw = a.switch("draw", 1)
        if draw:
            _set_u8(d, "draw_mode", a.enum(_DECAL_DRAW, draw[0]))
        if a.switch("light") is not None:
            _set_bit(d, "flags", 1)
        if a.switch("water") is not None:
            _set_bit(d, "flags", 2)
        if a.switch("ring") is not None:
            _set_bit(d, "flags", 5)
        repeat = a.switch("repeat", 1)
        if repeat:
            _set_bit(d, "flags", 3)
            _set_f(d, "texture_repeat", a.number(repeat[0]))
        offset = a.switch("offset", 1)
        if offset:
            d.texture_offset = a.vec2(offset[0])
        values = a.positional(0 if d.texture_key.value else 1)
        if values:
            key = self.textures.get(values[0].lower())
            if key is None:
                raise a.fail(f"No such texture: '{values[0]}'")
            _set_u32(d, "texture_key", key)

    # --- shake, light, dynamic particle, sequence sub-commands ----------------

    def _s_length(self, a: Args) -> None:
        s = self.shake
        if len(a.argv) < 2:
            raise a.fail("Not enough arguments")
        _set_f(s, "length", a.number(a.argv[1]))
        fade = a.switch("fade", 1)
        if fade:
            _set_f(s, "fade", a.number(fade[0]))
        if s.length.value < s.fade.value:
            s.fade = s.length

    def _s_amplitude(self, a: Args) -> None:
        self.shake.amplitude = _vector(a.number(v) for v in a.positional(1))

    def _s_frequency(self, a: Args) -> None:
        self.shake.frequency = _vector(a.number(v) for v in a.positional(1))

    def _s_aspect(self, a: Args) -> None:
        if len(a.argv) < 2:
            raise a.fail("Not enough arguments")
        _set_f(self.shake, "aspect", a.number(a.argv[1]))

    def _s_table(self, a: Args) -> None:
        if len(a.argv) < 2:
            raise a.fail("Not enough arguments")
        _set_u8(self.shake, "base_table", a.enum(_SHAKE_TABLES, a.argv[1]))

    def _l_strength(self, a: Args) -> None:
        self.light.strength = _vector(a.number(v) for v in a.positional(1))

    def _l_length(self, a: Args) -> None:
        l = self.light
        _set_f(l, "length", a.number(a.positional(1)[0]))
        # `length -fade` writes the shake scratch record in the game and does
        # not reach the light record, so it is only consumed here.
        fade = a.switch("fade", 1)
        if fade and self.shake is not None:
            _set_f(self.shake, "fade", a.number(fade[0]))

    def _l_color(self, a: Args) -> None:
        self.light.color = _vector(a.color(v) for v in a.positional(1))
        if a.command.name.endswith("255"):
            self.light.color = _vector(Vec3(f32(c.x * _ONE_OVER_255), f32(c.y * _ONE_OVER_255), f32(c.z * _ONE_OVER_255)) for c in self.light.color.items)

    def _dp_effect_base(self, a: Args) -> None:
        self.dynamic.base_name = WireString.from_text(a.positional(1)[0])

    def _dp_model(self, a: Args) -> None:
        d = self.dynamic
        names = a.positional()
        if not names:
            return
        keys = []
        for name in names:
            key = self.models.get(name.lower())
            if key is None:
                raise a.fail(f"No such model: '{name}'")
            keys.append(key)
        if len(keys) == 1:
            _set_u32(d, "model_key", keys[0])
            d.model_keys = _vector([])
        else:
            d.model_keys = _vector(keys)

    def _dp_mass(self, a: Args) -> None:
        _set_f(self.dynamic, "mass", a.number(a.positional(1)[0]))

    def _dp_friction(self, a: Args) -> None:
        d = self.dynamic
        values = a.positional(2)
        _set_f(d, "friction_min", a.number(values[0]))
        _set_f(d, "friction_max", a.number(values[1]))
        angular = a.switch("angular", 1)
        if angular:
            _set_f(d, "angular_friction", a.number(angular[0]))

    def _sq_wait(self, a: Args) -> None:
        values = a.positional(1)
        first = a.number(values[0])
        second = a.number(values[1]) if len(values) > 1 else first
        self._sq_append(Vec2(first, second), "")

    def _sq_play(self, a: Args) -> None:
        values = a.positional(2)
        first = a.number(values[1])
        second = a.number(values[2]) if len(values) > 2 else first
        self._sq_append(Vec2(first, second), values[0])

    def _sq_append(self, timing: Vec2, effect_name: str) -> None:
        item = SequenceItem(timing=timing, effect_name=WireString.from_text(effect_name))
        self.sequence.items = _vector(self.sequence.items.items + [item])

    # --- effect block and its children ---------------------------------------

    def _effect_block(self, a: Args) -> None:
        if self.effect is not None:
            raise a.fail("Can't nest effects! (Perhaps you meant visualEffect?)")
        name = a.positional(1)[0]
        e = default_effect_description()
        for switch, bit_ in (("viewRelative", 0), ("noAutoStop", 1), ("rigid", 3), ("ignoreOrientation", 6), ("hardStop", 2), ("noPropagate", 4), ("applyCursor", 5), ("noLODStop", 7)):
            if a.switch(switch) is not None:
                _set_bit(e, "flags", bit_)
        message = a.switch("startMessage", 1)
        if message:
            for attribute, value in zip(("start_message_1", "start_message_2", "start_message_3"), message):
                _set_u32(e, attribute, a.uint(value))
        if a.switch("manualRestart") is not None:
            _set_bit(e, "flags", 8)
        remap = self.remaps.get(name.lower())
        if remap is not None:
            _set_u32(e, "priority", remap[0])
            if remap[1]:
                name = remap[1]
        else:
            priority = a.switch("priority", 1)
            if priority:
                _set_u32(e, "priority", a.ranged_int(priority[0], 1, 5))
        self.effect = e
        self.effect_group = self.select_group = self.select_counter = 0
        self.select_start = 0
        self.system_sequence = False
        self._run_body(a.command, "effect")
        self._commit_effect(name, e)
        self.effect = None

    def _commit_effect(self, name: str, e: EffectDescription) -> None:
        """`AddEffectDescription`: lowercase names, replace a description with
        the same name and priority or append one, then resolve child indices."""

        key_name = name.lower()
        key = (key_name, e.priority.value)
        if key in self.effect_by_key:
            index = self.effect_by_key[key]
            self._assign_children(index, self.resource.effect_descriptions.items[index], e)
            self.resource.effect_descriptions.items[index] = e
        else:
            index = len(self.resource.effect_descriptions.items)
            if index == self.effect_vector_capacity:
                self._grow_effect_vector(index)
            self.child_capacities.append(len(e.descriptions.items))
            self.effect_by_key[key] = index
            self.effect_names.setdefault(key_name, []).append(index)
            self.resource.effect_descriptions = _vector(self.resource.effect_descriptions.items + [e])
            self.name_table.insert_equal(key_name, index)
        e.chain_effect = WireString.from_text((e.chain_effect.decoded or "").lower()) if e.chain_effect.raw_bytes else e.chain_effect
        for d in e.descriptions.items:
            if d.description_index.value != 0xFFFFFFFF:
                continue
            lowered = (d.name.decoded or "").lower()
            d.name = WireString.from_text(lowered) if d.name.raw_bytes else d.name
            kind = d.component_type.value
            table = {0: self.particle_names, 16: self.dynamic_names, 1: self.decal_names, 6: self.sequence_names}.get(kind)
            if kind == 2:
                d.description_index = make_raw_u32(0)
            elif table is not None and lowered in table:
                d.description_index = make_raw_u32(table[lowered])
        events = []
        for event in e.events.items:
            lowered = (event.name.decoded or "").lower()
            value = event.value
            if event.flags.value & 1 and lowered in self.shake_names:
                value = make_raw_u32(self.shake_names[lowered])
            elif event.flags.value & 0b1100 and lowered in self.light_names:
                value = make_raw_u32(self.light_names[lowered])
            events.append(
                EventRecord(flags=event.flags, name=WireString.from_text(lowered) if event.name.raw_bytes else event.name, time=event.time, value=value)
            )
        e.events = _vector(events)

    def _assign_children(self, index: int, previous: EffectDescription, new: EffectDescription) -> None:
        """`vector<cDescriptionRec>::operator=` over an existing effect.

        `cS3DTransform::operator=` (Mac `0x0062BA46`) adds one to its own
        counter and never copies the source's, while its copy constructor
        (`0x0066039A`) zeroes it. The counter is the serialized `revision`,
        so it records how often a child slot was assigned over.
        """

        old, fresh = previous.descriptions.items, new.descriptions.items
        if len(fresh) > self.child_capacities[index]:
            self.child_capacities[index] = len(fresh)  # reallocated, every element copy-constructed
            return
        for before, after in zip(old, fresh):
            after.legacy_transform.revision = make_raw_u32((before.legacy_transform.revision.value + 1) & 0xFF)

    def _grow_effect_vector(self, size: int) -> None:
        """The effect vector doubles when full, and its copy constructors
        zero every child counter and shrink each child vector to fit."""

        self.effect_vector_capacity = size + max(size, 1)
        for index, effect in enumerate(self.resource.effect_descriptions.items):
            self.child_capacities[index] = len(effect.descriptions.items)
            for d in effect.descriptions.items:
                d.legacy_transform.revision = make_raw_u32(0)

    def _child_record(self, a: Args, name: str, component_type: int) -> DescriptionRecord:
        d = default_description_record()
        d.name = WireString.from_text(name)
        d.component_type = make_raw_u8(component_type)
        d.selection_group = make_raw_u16(self.select_group)
        return d

    def _describe(self, a: Args, d: DescriptionRecord) -> None:
        """ParseDescRecOptions (Mac `0x00401D2C`)."""

        t = d.legacy_transform
        offset = a.switch("offset", 1)
        if offset:
            t.translation = a.vec3(offset[0])
        for switch, sequence in (("rotateX", "x"), ("rotateY", "y"), ("rotateZ", "z"), ("rotateXYZ", "xyz"), ("rotateZXY", "zxy")):
            values = a.switch(switch, len(sequence))
            if values:
                for axis, text in zip(sequence, values):
                    _rotate(t.matrix, axis, a.number(text))
        scale = a.switch("scale", 1)
        if scale:
            t.scale = a.number(scale[0])
        lod_range = a.switch("lodRange", 2)
        lod = a.switch("lod", 1) if lod_range is None else None
        if (lod_range or lod) and self.select_group:
            raise a.fail("Can't specify LOD in a select")
        if lod_range:
            _set_u8(d, "lod", a.uint(lod_range[0]))
            _set_u8(d, "lod_range", (a.uint(lod_range[1]) + 1))
        elif lod:
            value = a.uint(lod[0])
            _set_u8(d, "lod", value)
            _set_u8(d, "lod_range", value + 1)
        else:
            _set_u8(d, "lod", 1)
            _set_u8(d, "lod_range", 6)
        emit_scale = a.switch("emitScale", 1)
        if emit_scale:
            first = a.number(emit_scale[0])
            _set_f(d, "emit_scale_min", first)
            _set_f(d, "emit_scale_max", a.number(emit_scale[1]) if len(emit_scale) > 1 else first)
        size_scale = a.switch("sizeScale", 1)
        if size_scale:
            first = a.number(size_scale[0])
            _set_f(d, "size_scale_min", first)
            _set_f(d, "size_scale_max", a.number(size_scale[1]) if len(size_scale) > 1 else first)
        probability = a.switch("prob", 1)
        if probability:
            if not self.select_group:
                raise a.fail("-prob only valid inside a select group")
            d.probability = make_raw_u16(_bias_round(f32(a.number(probability[0]) * 65535.0)) & 0xFFFF)
        if a.switch("ignoreLength") is not None:
            _set_bit(d, "flags", 0)
        if a.switch("respectLength") is not None:
            _set_bit(d, "flags", 0, False)

    def _push_child(self, d: DescriptionRecord) -> None:
        self.effect.descriptions = _vector(self.effect.descriptions.items + [d])

    def _named_child(self, a: Args, table: Dict[str, int], kind: int, unknown: str, *, system_sequence: bool = True, shells: bool = False) -> None:
        name = a.positional(1)[0]
        if name.lower() not in table:
            raise a.fail(unknown % name)
        d = self._child_record(a, name, kind)
        if system_sequence and self.system_sequence:
            _set_bit(d, "flags", 1)
        self._describe(a, d)
        if shells:
            shell = a.switch("shells", 1)
            if shell:
                d.shell_count = make_raw_u16(a.uint(shell[0]) & 0xFFFF)
                if len(shell) > 1:
                    d.shell_offset = make_raw_u16(_round_shell_offset(a.number(shell[1])) & 0xFFFF)
        self._push_child(d)

    def _c_particle(self, a: Args) -> None:
        self._named_child(a, self.particle_names, 0, "Unknown particle definition: %s", shells=True)

    def _c_decal(self, a: Args) -> None:
        self._named_child(a, self.decal_names, 1, "Unknown decal definition: %s", system_sequence=False)

    def _c_dynamic(self, a: Args) -> None:
        self._named_child(a, self.dynamic_names, 16, "Unknown particle definition: %s")

    def _c_visual(self, a: Args) -> None:
        name = a.positional(1)[0]
        if name.lower() not in self.effect_names:
            raise a.fail(f"Unknown visual effect: {name}")
        d = self._child_record(a, name, 2)
        self._describe(a, d)
        self._push_child(d)

    def _c_sequence(self, a: Args) -> None:
        name = a.positional(1)[0]
        if name.lower() not in self.sequence_names:
            raise a.fail(f"No such description: '{name}'")
        d = self._child_record(a, name, 6)
        self._describe(a, d)
        self._push_child(d)

    def _event(self, a: Args, name: str, flag_bit: int) -> EventRecord:
        event = default_event_record()
        event.flags = event.flags.replace(1 << flag_bit)
        event.name = WireString.from_text(name)
        self.effect.events = _vector(self.effect.events.items + [event])
        return event

    def _c_shake(self, a: Args) -> None:
        name = a.positional(1)[0]
        if name.lower() not in self.shake_names:
            raise a.fail(f"unknown shake definition: {name}")
        event = self._event(a, name, 0)
        if a.switch("noEpicentre") is None and a.switch("noEpicenter") is None:
            event.flags = event.flags.replace(event.flags.value | 2)

    def _c_flash(self, a: Args) -> None:
        name = a.positional(1)[0]
        if name.lower() not in self.light_names:
            raise a.fail(f"unknown light definition: {name}")
        event = self._event(a, name, 2)
        epicentre = a.switch("epicentre")
        if epicentre is None:
            epicentre = a.switch("epicenter")
        if epicentre is not None:
            event.flags = event.flags.replace(event.flags.value | 2)
            event.time = make_raw_f32(a.number(epicentre[0]) if epicentre else 1000.0)

    def _c_tint(self, a: Args) -> None:
        name = a.positional(1)[0]
        if name.lower() not in self.light_names:
            raise a.fail(f"unknown light definition: {name}")
        self._event(a, name, 3)

    def _c_chain(self, a: Args) -> None:
        self.effect.chain_effect = WireString.from_text(a.positional(1)[0])

    def _anon(self, a: Args, vector_attr: str, record, component_type: int, flags_bit0: bool) -> None:
        components = self.resource.components
        vector = getattr(components, vector_attr)
        d = self._child_record(a, "", component_type)
        d.name = WireString(decoded="", raw_bytes=b"", encoding="utf8", framing=None, valid=True, changed=True)
        d.description_index = make_raw_u32(len(vector.items))
        if flags_bit0:
            _set_bit(d, "flags", 0)
        self._describe(a, d)
        setattr(components, vector_attr, _vector(vector.items + [record]))
        self._push_child(d)

    def _c_brush(self, a: Args) -> None:
        b = default_brush()
        name = a.switch("name", 1)
        if name is None:
            raise a.fail("need at least -name for an anonymous brush effect")
        key = name[0].lower()
        if key not in self.brushes and key + "_b" not in self.brushes:
            raise a.fail(f"No such brush: '{name[0]}'")
        _set_u32(b, "key", self.brushes.get(key, self.brushes.get(key + "_b", 0)))
        rate = a.switch("rate", 1)
        if rate:
            _set_f(b, "rate", a.number(rate[0]))
        apply_switch = a.switch("apply", 1)
        if apply_switch:
            _set_f(b, "rate", a.number(apply_switch[0]))
            _set_u8(b, "mode", 1)
        length = a.switch("length", 1)
        if length:
            _set_f(b, "length", a.number(length[0]))
        zoom = a.switch("zoom", 1)
        if zoom:
            _set_u32(b, "zoom", a.ranged_int(zoom[0], 1, 5) - 1)
        strength = a.switch("strength", 1)
        if strength:
            b.strength = a.float_range(strength)
        width = a.switch("width", 1)
        if width:
            b.width = a.float_range(width)
        level = a.switch("level", 1)
        if level:
            _set_f(b, "level", a.number(level[0]))
        self._anon(a, "brushes", b, 3, False)

    def _c_sound(self, a: Args) -> None:
        if a.positional():
            raise a.fail("sound description unimplemented")
        s = default_sound()
        name = a.switch("name", 1)
        if name is None:
            raise a.fail("Need at least -name for anonymous soundEffect")
        key = name[0].lower()
        if key not in self.sounds:
            raise a.fail(f"Unknown sound {name[0]}")
        _set_u32(s, "resource_key", self.sounds[key])
        rate = a.switch("locationUpdateRate", 1)
        if rate:
            value = a.number(rate[0])
            _set_f(s, "location_update_rate", f32(1.0 / value) if value > 0.0 else 0.0)
        length = a.switch("length", 1)
        if length:
            _set_f(s, "length", a.number(length[0]))
        self._anon(a, "sounds", s, 7, s.length.value == 0.0)

    def _c_automata(self, a: Args) -> None:
        d = default_attractor()
        name = a.switch("name", 1)
        group = a.switch("group", 1) if name is None else None
        if name is None and group is None:
            raise a.fail("Need at least -name or -group for anonymous attractor effect")
        values = name if name is not None else group
        d.name = WireString.from_text(values[0])
        if group is not None:
            d.selector = make_raw_u8(1)
        self._anon(a, "attractors", d, 4, True)

    def _c_camera(self, a: Args) -> None:
        c = default_camera()
        if a.switch("slave") is not None:
            _set_bit(c, "flags", 3)
        if a.switch("target") is not None:
            _set_bit(c, "flags", 2)
        radius = a.switch("attachRadius", 1)
        if radius:
            _set_f(c, "attach_radius", a.number(radius[0]))
        zoom = a.switch("zoom", 1)
        if zoom:
            _set_u8(c, "zoom", a.ranged_int(zoom[0], 1, 5) - 1)
            _set_bit(c, "flags", 0)
        rotation = a.switch("rotation", 1)
        if rotation:
            # The Mac text parser writes rotation into the zoom byte (+0x10).
            _set_u8(c, "zoom", a.ranged_int(rotation[0], 0, 3))
            _set_bit(c, "flags", 1)
        self._anon(a, "cameras", c, 8, True)

    def _c_scrubber(self, a: Args) -> None:
        s = default_scrubber()
        any_option = False
        for switch, attribute in (("demolish", "demolish"), ("burn", "burn"), ("toxic", "toxic")):
            value = a.switch(switch, 1)
            if value:
                _set_u32(s, attribute, _uint_from_float(a.number(value[0])))
                any_option = True
        fire = a.switch("extinguishFire", 1)
        if fire:
            _set_u32(s, "extinguish_fire", a.uint(fire[0]))
            any_option = True
        for switch, bit_ in (("pauseSim", 4), ("pauseSimHidden", 5), ("pauseClock", 6)):
            value = a.switch(switch)
            if value is not None:
                _set_bit(s, "flags", bit_)
                if value:
                    _set_f(s, "pause_duration", a.number(value[0]))
                any_option = True
        message = a.switch("message", 1)
        if message:
            _set_u32(s, "message_1", a.uint(message[0]))
            if len(message) > 1:
                _set_u32(s, "message_2", a.uint(message[1]))
            any_option = True
        blob = a.switch("blob", 3)
        if blob:
            _set_u32(s, "map_index", a.ranged_int(blob[0], 1, 8))
            _set_f(s, "map_value", a.number(blob[1]))
            extent = a.number(blob[2])
            s.map_half_extents = Vec2(extent, extent)
            if len(blob) > 3:
                _set_f(s, "map_spread", a.number(blob[3]))
            any_option = True
        rect = a.switch("rect", 4)
        if rect:
            _set_u32(s, "map_index", a.ranged_int(rect[0], 1, 8))
            _set_f(s, "map_value", a.number(rect[1]))
            s.map_half_extents = Vec2(a.number(rect[2]), a.number(rect[3]))
            if len(rect) > 4:
                _set_f(s, "map_spread", a.number(rect[4]))
        elif not any_option:
            raise a.fail("Need some options for anonymous scrubber effect")
        for switch, bit_ in (("noNetworks", 0), ("noFlora", 1), ("dezone", 2), ("single", 3)):
            if a.switch(switch) is not None:
                _set_bit(s, "flags", bit_)
        explode = a.switch("explode") is not None
        action, effect_id = (0x1300, 2) if explode else (0, 1)
        if a.switch("createRubble") is not None:
            action = 0x1300
        if a.switch("createBurntRubble") is not None:
            action |= 0x300
        identifier = a.switch("demolishEffectID", 1)
        if identifier:
            effect_id = a.uint(identifier[0]) & 0xFF
        _set_u32(s, "action", action | effect_id)
        minimum = a.switch("minDemolishSize", 1)
        if minimum:
            _set_f(s, "min_size", a.number(minimum[0]))
        maximum = a.switch("maxDemolishSize", 1)
        if maximum:
            _set_f(s, "max_size", a.number(maximum[0]))
        self._anon(a, "scrubbers", s, 5, True)

    def _c_select(self, a: Args) -> None:
        self.select_counter += 1
        self.select_group = self.select_counter
        self.select_start = len(self.effect.descriptions.items)
        self._run_body(a.command, "select")
        self._finish_select()
        self.select_group = 0

    def _finish_select(self) -> None:
        """`cGroupSelectCommand::EndBlock`: unassigned children share what
        the explicit probabilities leave, the last child absorbs rounding."""

        items = self.effect.descriptions.items
        # The game counts explicit children here instead of summing their
        # probabilities (Mac 0x0077DA24), which is why the last child of
        # vanilla selects comes up short. The behaviour is reproduced as is.
        assigned = 0
        unassigned = 0
        for d in items[self.select_start :]:
            if d.probability.value == 0:
                unassigned += 1
            else:
                assigned += 1
        if unassigned:
            share = (0x10000 - assigned) // unassigned
            for d in items[self.select_start :]:
                if d.probability.value == 0:
                    d.probability = make_raw_u16(share & 0xFFFF)
                    assigned += share
        if len(items) > self.select_start:
            last = items[-1]
            last.probability = make_raw_u16((last.probability.value + ((~assigned) & 0xFFFF)) & 0xFFFF)

    def _c_particle_sequence(self, a: Args) -> None:
        self.system_sequence = True
        self._run_body(a.command, "particleSequence")
        self.system_sequence = False

    def _noop_body(self, a: Args) -> None:
        self._run_body(a.command, a.command.name)

    def _unsupported(self, a: Args) -> None:
        # The game merges the loaded resource into the collection being
        # saved (`AddToCollection`, Mac 0x003E4120), and a resource stores no
        # names for its pools, so compiling this would only copy another
        # resource into the output.
        raise a.fail("loadResource is not supported by the compiler: it would copy the whole loaded resource into this one")

    def _no_record(self, a: Args) -> None:
        """Commands the game accepts that change nothing in the resource."""

        a.argv = a.argv[:1]

    def _set_priority(self, a: Args) -> None:
        values = a.positional(2)
        self.remaps[values[0].lower()] = (a.integer(values[1]), values[2] if len(values) > 2 else "")


def _cube(center: Vec3, half: float) -> Bounds3:
    return Bounds3(Vec3(f32(center.x - half), f32(center.y - half), f32(center.z - half)), Vec3(f32(half + center.x), f32(half + center.y), f32(half + center.z)))


def _uint_from_float(value: float) -> int:
    value = max(value, 0.0)
    if value >= 4294967296.0:
        return 0xFFFFFFFF
    return int(value)


def _bias_round(value: float) -> int:
    """The game's float-to-int: add `0xC00000` and read the mantissa bits, so
    in the normal range it rounds to nearest (ties to even)."""

    return struct.unpack("<i", struct.pack("<f", f32(value + 12582912.0)))[0] - 0x4B400000


def _round_shell_offset(value: float) -> int:
    # `-shells` offset: the same bias, shifted by 0.5, then pulled back one
    # step when the bias lands exactly on the input.
    result = _bias_round(f32(value + 0.5))
    return result - 1 if value == float(result - 1) else result


def _canonical_float(value: float) -> str:
    text = f"{value:.9g}"
    return text


_BLOCK_TABLES: Dict[str, Dict[str, Callable]] = {
    "particles": {
        "zoom": FxCompiler._p_zoom,
        "color": FxCompiler._p_color,
        "colour": FxCompiler._p_color,
        "color255": FxCompiler._p_color,
        "colour255": FxCompiler._p_color,
        "alpha": FxCompiler._p_alpha,
        "alpha255": FxCompiler._p_alpha,
        "size": FxCompiler._p_size,
        "aspect": FxCompiler._p_aspect,
        "rotate": FxCompiler._p_rotate,
        "source": FxCompiler._p_source,
        "emit": FxCompiler._p_emit,
        "force": FxCompiler._p_force,
        "warp": FxCompiler._p_warp,
        "randomWalk": FxCompiler._p_random_walk,
        "stretch": FxCompiler._p_stretch,
        "life": FxCompiler._p_life,
        "rate": FxCompiler._p_rate,
        "inject": FxCompiler._p_inject,
        "maintain": FxCompiler._p_maintain,
        "texture": FxCompiler._p_texture,
        "model": FxCompiler._p_model,
        "align": FxCompiler._p_align,
        "collide": FxCompiler._p_collide,
        "terrainRepel": FxCompiler._p_terrain_repel,
        "effectBase": FxCompiler._p_effect_base,
        "timedEffect": FxCompiler._p_timed_effect,
    },
    "decal": {
        "color": FxCompiler._d_color,
        "color255": FxCompiler._d_color,
        "colour": FxCompiler._d_color,
        "colour255": FxCompiler._d_color,
        "alpha": FxCompiler._d_alpha,
        "alpha255": FxCompiler._d_alpha,
        "size": FxCompiler._d_size,
        "aspect": FxCompiler._d_aspect,
        "rotate": FxCompiler._d_rotate,
        "life": FxCompiler._d_life,
        "texture": FxCompiler._d_texture,
    },
    "shake": {
        "length": FxCompiler._s_length,
        "amplitude": FxCompiler._s_amplitude,
        "frequency": FxCompiler._s_frequency,
        "shakeAspect": FxCompiler._s_aspect,
        "table": FxCompiler._s_table,
    },
    "light": {
        "strength": FxCompiler._l_strength,
        "length": FxCompiler._l_length,
        "color": FxCompiler._l_color,
        "color255": FxCompiler._l_color,
        "colour": FxCompiler._l_color,
        "colour255": FxCompiler._l_color,
    },
    "dynamicParticle": {
        "effectBase": FxCompiler._dp_effect_base,
        "model": FxCompiler._dp_model,
        "mass": FxCompiler._dp_mass,
        "friction": FxCompiler._dp_friction,
    },
    "sequence": {"wait": FxCompiler._sq_wait, "play": FxCompiler._sq_play},
    "effectGroup": {"instance": FxCompiler._effect_instance},
    "effect": {
        "particleEffect": FxCompiler._c_particle,
        "dynamicParticleEffect": FxCompiler._c_dynamic,
        "decalEffect": FxCompiler._c_decal,
        "visualEffect": FxCompiler._c_visual,
        "sequenceEffect": FxCompiler._c_sequence,
        "shakeEffect": FxCompiler._c_shake,
        "flashEffect": FxCompiler._c_flash,
        "tintEffect": FxCompiler._c_tint,
        "chainEffect": FxCompiler._c_chain,
        "soundEffect": FxCompiler._c_sound,
        "brushEffect": FxCompiler._c_brush,
        "scrubberEffect": FxCompiler._c_scrubber,
        "demolishEffect": FxCompiler._c_scrubber,
        "gameEffect": FxCompiler._c_scrubber,
        "mapEffect": FxCompiler._c_scrubber,
        "automataEffect": FxCompiler._c_automata,
        "cameraEffect": FxCompiler._c_camera,
        "select": FxCompiler._c_select,
        "particleSequence": FxCompiler._c_particle_sequence,
    },
}
_TOP_LEVEL: Dict[str, Callable] = {
    "textureID": lambda self, a: self._id_map(a, self.textures),
    "modelID": lambda self, a: self._id_map(a, self.models),
    "soundID": lambda self, a: self._id_map(a, self.sounds),
    "brushID": lambda self, a: self._id_map(a, self.brushes),
    "effectID": FxCompiler._effect_id,
    "effectGroup": FxCompiler._effect_group_block,
    "messageTrigger": FxCompiler._message_trigger,
    "camera": FxCompiler._camera,
    "setPriority": FxCompiler._set_priority,
    "effect": FxCompiler._effect_block,
    "particles": FxCompiler._particles_block,
    "dynamicParticle": FxCompiler._dynamic_block,
    "decal": FxCompiler._decal_block,
    "shake": FxCompiler._shake_block,
    "light": FxCompiler._light_block,
    "sequence": FxCompiler._sequence_block,
    "effectsResource": FxCompiler._noop_body,
    "namespace": FxCompiler._namespace,
    "set": FxCompiler._set_var,
    "seti": FxCompiler._set_var,
    "setf": FxCompiler._set_var,
    "setc": FxCompiler._set_var,
    "setv3": FxCompiler._set_var,
    "create": FxCompiler._create,
    "arrayCreate": FxCompiler._array_create,
    "eval": FxCompiler._eval,
    "renderprop": FxCompiler._no_record,
    "testEffect": FxCompiler._no_record,
    "trace": FxCompiler._no_record,
    "version": FxCompiler._no_record,
    "loadResource": FxCompiler._unsupported,
}


def compile_source(text: str, *, file: str = "", include_dir: Optional[str] = None) -> EffDirResource:
    """Compile `.fx` source text to a resource model, or raise `FxError`.

    `include` paths are relative to `include_dir` (default: the working
    directory).
    """

    source, origins = expand_includes(text, file, include_dir or os.getcwd())
    compiler = FxCompiler(file=file)
    compiler.run(parse_file(source, file=file, origins=origins))
    return compiler.finish()


def compile_to_bytes(text: str, *, file: str = "", include_dir: Optional[str] = None) -> bytes:
    """Compile `.fx` source text to packed EFFDIR bytes."""

    from ..model.resource import write_resource

    return write_resource(compile_source(text, file=file, include_dir=include_dir))
