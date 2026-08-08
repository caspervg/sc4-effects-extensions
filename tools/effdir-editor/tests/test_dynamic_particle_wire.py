import struct

from effdir_editor.model.dynamic_particle import (
    default_dynamic_particle,
    read_dynamic_particle,
    write_dynamic_particle,
)
from effdir_editor.bindings.catalog import find_bindings
from effdir_editor.wire import ReadCursor, WriteCursor


def _mac_wire_fixture() -> bytes:
    # Mac operator>> 0x004B8ADA / operator<< 0x004B8A2E:
    # flags, string, model key, model-key vector, then six floats.
    return b"".join(
        [
            struct.pack("<I", 0x45),
            struct.pack("<I", 4),
            b"base",
            struct.pack("<I", 0x12345678),
            struct.pack("<I2I", 2, 0x11111111, 0x22222222),
            struct.pack("<6f", 2.5, 3.5, 0.1, 0.2, 0.3, 4.5),
        ]
    )


def test_dynamic_particle_uses_mac_non_monotonic_wire_order():
    payload = _mac_wire_fixture()
    cursor = ReadCursor(payload)

    descriptor = read_dynamic_particle(cursor)

    assert cursor.at_end()
    assert descriptor.flags.value == 0x45
    assert descriptor.base_name.decoded == "base"
    assert descriptor.model_key.value == 0x12345678
    assert descriptor.model_keys.items == [0x11111111, 0x22222222]
    assert descriptor.mass.value == 2.5
    assert descriptor.value_14.value == 3.5
    assert descriptor.friction_min.value == struct.unpack("<f", struct.pack("<f", 0.1))[0]
    assert descriptor.friction_max.value == struct.unpack("<f", struct.pack("<f", 0.2))[0]
    assert descriptor.angular_friction.value == struct.unpack("<f", struct.pack("<f", 0.3))[0]
    assert descriptor.value_24.value == 4.5

    writer = WriteCursor()
    write_dynamic_particle(writer, descriptor)
    assert writer.getvalue() == payload


def test_dynamic_particle_default_mass_matches_mac_constructor():
    assert default_dynamic_particle().mass.value == 1.0


def test_dynamic_particle_parser_semantics_are_exposed_as_bindings():
    assert [binding.id for binding in find_bindings("DynamicParticleDescriptor", "base_name")] == [
        "dynamic_particle.effectBase"
    ]
    assert [binding.id for binding in find_bindings("DynamicParticleDescriptor", "mass")] == [
        "dynamic_particle.mass"
    ]
    assert [binding.id for binding in find_bindings("DynamicParticleDescriptor", "model_key")] == [
        "dynamic_particle.model"
    ]
    assert [binding.id for binding in find_bindings("DynamicParticleDescriptor", "model_keys")] == [
        "dynamic_particle.model"
    ]
    assert [binding.id for binding in find_bindings("DynamicParticleDescriptor", "friction_min")] == [
        "dynamic_particle.friction"
    ]
    assert find_bindings("DynamicParticleDescriptor", "flags") == []
    assert find_bindings("DynamicParticleDescriptor", "value_14") == []
    assert find_bindings("DynamicParticleDescriptor", "value_24") == []
