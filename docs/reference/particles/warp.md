# `warp`

Status: `Confirmed`

`warp` is a particle subcommand for per-particle geometric warping and wiggle
behavior.

## Syntax

```fx
warp [options...]
```

Recovered options:

- `-screw <float>`
- `-wiggle <period> <strength> <radius> <phase>`
- `-wiggleDir <period> <dirVec3> [varyVec3]`
- `-wiggleVerts`
- `-uv <speed> <vec2>`
- `-alpha <dirVec3> <0..1> [0..1 ...]`

## Recovered behavior

### `-screw <float>`

Stores a scaled screw factor:

- `value * 0.02`

at the same field used by the particle force-side screw control.

### `-wiggle <period> <strength> <radius> <phase>`

Builds a wiggle record and appends it to the particle description's wiggle list.

Recovered behavior:

- first argument becomes the wiggle period / timing value
- second becomes a scalar strength-like field
- third becomes a radius / amplitude
- fourth is parsed as a ranged float `0..1`
- that phase value is converted into a circular X/Z direction with `cos` / `sin`

So the fourth argument is effectively a normalized phase around the circle.

### `-wiggleDir <period> <dirVec3> [varyVec3]`

Builds a wiggle record with an explicit direction vector.

Recovered behavior:

- first argument becomes the wiggle period / timing value
- second is a direction vector
- optional third argument is another vector stored as the wiggle variation /
  secondary vector
- if the third argument is omitted, that secondary vector is zero

### `-wiggleVerts`

Sets secondary warp flag bit `8`.

This appears to enable vertex-level warping behavior.

### `-uv <speed> <vec2>`

Stores:

- a float at `+0x234`
- a vector2 at `+0x238/+0x23c`

and sets secondary warp flag bit `8`.

This looks like UV scrolling or UV-space warping.

### `-alpha <dirVec3> <0..1> [0..1 ...]`

Recovered behavior:

- normalizes the supplied vector3 and stores it at `+0x240..+0x248`
- clears a float list at `+0x24c`
- parses each remaining argument as a ranged float `0..1`
- appends those floats to the list
- sets secondary warp flag bit `8`

This appears to be a direction plus one or more alpha-warp control values.

## Likely field mapping

- `+0x228` -> wiggle record vector
- `+0x234` -> UV warp speed / scalar
- `+0x238/+0x23c` -> UV vector2
- `+0x240..+0x248` -> normalized alpha warp direction
- `+0x24c` -> alpha warp float list
- `+0x128` bit `8` -> secondary warp-enabled / vertex-warp-enabled flag

## Example

```fx
particles warped_sparks
    source -point
    emit -dir "0 1 0" 0.2 -speed 40
    warp -wiggle 0.4 0.15 0.2 0.25 -wiggleVerts -uv 0.5 "1 0"
    texture spark_tex -draw additive
end
```

## Notes

- `warp` does not define spawn timing or force on its own; it layers on top of
  a normal particle setup
- several options set the same secondary warp flag, so these appear to be
  related submodes of the same subsystem
