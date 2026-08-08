# `force`

Status: `Confirmed`

`force` configures persistent forces and several specialized shaping systems.

## Simple force options

- `-reset`
- `-gravity <float>`
- `-wind <vec3> [float]`
- `-global_wind <float>`
- `-drag <float>`
- `-screw <float>`
- `-bomb <float> [vec3]`

## Attractor family

- `-attractor <float> <float...>`
- `-alphaAttractor <float> <float...>`
- `-motherDuck <float> <float...>`
- `-automata <uint> <float>`

Recovered behavior:

- `-attractor` stores a strength value plus a float curve used during particle
  update
- `-alphaAttractor` uses the same strength-plus-curve storage family, but also
  enables a dedicated runtime flag for alpha-driven attraction behavior
- `-motherDuck` also stores a strength value plus a float curve, but enables a
  different runtime flag than plain `-attractor`
- at runtime, `-motherDuck` adds a pull toward the effect's reference point,
  effectively acting like a flocking or follow-the-leader force centered on the
  emitter / effect origin

Practical interpretation:

- use `-attractor` when you want a generic radial pull driven by a strength
  curve
- use `-motherDuck` when you want particles to stay gathered around the moving
  effect origin
- `-motherDuck` is not part of the separate top-level attractor-effect system;
  it is a particle force option parsed by the particle force command

Example:

```fx
particles duck_demo
    force
        -motherDuck 6.0 1.0 0.7 0.2 0.0
        -drag 0.15
    end
end
```

The recovered parser accepts:

- one leading strength float
- one or more additional float values, interpreted as the runtime curve data

## Tractor / path family

- `-tractor <vec3> <float|vec3> [float]`
- `-tractorRel <vec3> <float|vec3> [float]`
- `-tractorResetSpeed <float>`
- `-tractorTimeScale <float>`

Recovered behavior:

- `-tractor` appends an absolute tractor point
- `-tractorRel` appends a tractor point relative to the previous tractor point
  position
- each tractor point stores:
  position, tangent / velocity vector, start time, and end time
- runtime evaluation is performed by `cSC4ParticlesEffect::ApplyTractorForce`,
  which Hermite-interpolates particle position and velocity along the tractor
  sequence

Second argument forms:

- if the second argument is a single float, the parser treats it as a
  distance-like scalar and derives the tangent automatically
- if the second argument is a vec3, the parser uses it as the explicit tangent
  vector
- if a third float is present, it advances the tractor segment timing

Practical interpretation:

- `tractor` is path steering, not just a scalar force
- `tractorRel` is the path-chaining form
- together they are the closest thing the particle system has to an authored
  spline path

### `-tractor`

Absolute path points:

```fx
particles tractor_demo
    force
        -tractor "0 0 0" 4.0
        -tractor "0 3 0" 3.0 0.5
        -tractor "2 5 0" "1 0 0" 0.5
    end
end
```

Interpretation:

- first point at `0 0 0`, with an auto-derived tangent of length `4.0`
- second point at `0 3 0`, again with an auto-derived tangent and an explicit
  time advance
- third point at `2 5 0`, with an explicit tangent vector and explicit time
  advance

### `-tractorRel`

Relative chaining:

```fx
particles tractor_rel_demo
    force
        -tractor "0 0 0" 2.0
        -tractorRel "1 0 0" 2.0
        -tractorRel "0 2 0" "0 1 0" 0.25
    end
end
```

Interpretation:

- the first point is absolute
- the second point is offset by `1 0 0` from the first point
- the third point is offset by `0 2 0` from the previous point and uses an
  explicit tangent vector

### `-tractorResetSpeed`

```fx
particles tractor_reset_demo
    force
        -tractor "0 0 0" 3.0
        -tractor "0 4 0" 3.0 0.5
        -tractorResetSpeed 10.0
    end
end
```

Recovered interpretation:

- stores a reset / catch-up speed threshold used by runtime tractor evaluation
- when particles drift too far from the intended tractor segment, this value
  helps the runtime re-sync traversal along the path

### `-tractorTimeScale`

```fx
particles tractor_time_demo
    force
        -tractor "0 0 0" 2.0
        -tractor "0 6 0" 2.0 1.0
        -tractorTimeScale 0.5
    end
end
```

Recovered behavior:

- rescales tractor timing
- also rescales already stored tractor tangents and segment times

Practical note:

- author tractor points first, then apply `-tractorTimeScale` once to retime the
  whole tractor path

## Terrain / explosion shaping

- `-terrainRepel <float> <float> [float]`
- `-explosion <float> <float...>`
- `-explosionFront <float> <float>`
