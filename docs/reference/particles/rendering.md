# `texture`, `model`, and `align`

Status: `Confirmed`

These particle subcommands control drawing mode, render assets, and orientation.

## Shared draw options

Recovered for `texture` and `model`:

- `-draw <enum>`
- `-light`
- `-noCull`
- `-sortOffset <float>`

## `texture`

- resolves a symbolic texture name through `textureID`
- also supports:
  - `-vflip`
  - `-hflip`

## `model`

Recovered syntax:

```fx
model <modelName> [moreModelNames...]
    -draw <enum>
    -light
    -noCull
    -sortOffset <float>
    -fakePerspective
    -moveEntireSlave
    -slaveApplyAlpha
    -applyAlpha
    -modelSpeed <float>
    -modelSpeedStatic <float>
    -sustain
    -applyLighting
    -noCullFaces
```

Recovered behavior:

- only valid inside a `particles` block
- sets particle secondary flag bit `0`
- sets particle type byte at `+0x1f4` to `3`
- resolves all non-switch arguments through the parser's `modelID` map
- model name lookup is case-insensitive
- unknown model names throw:
  `No such model: '%s'`
- if exactly one model name is supplied:
  - stores it directly at `+0x1f0`
  - clears the multi-model vector at `+0x2f8`
- if more than one model name is supplied:
  - stores them into the vector at `+0x2f8`

Recovered model-specific switches:

- `-fakePerspective`
- `-moveEntireSlave`
- `-slaveApplyAlpha`
- `-applyAlpha`
- `-modelSpeed <float>`
- `-modelSpeedStatic <float>`
- `-sustain`
- `-applyLighting`
- `-noCullFaces`

Recovered notes on the switches:

- `-slaveApplyAlpha` and `-applyAlpha` are treated equivalently
- `-modelSpeed` stores a float at `+0x2f4` and sets secondary flag bit `6`
- `-modelSpeedStatic` stores the same float field without setting that extra
  bit
- `-applyLighting` sets secondary flag bit `2`
- `-moveEntireSlave` sets secondary flag bit `3`
- `-slaveApplyAlpha` / `-applyAlpha` set secondary flag bit `4`
- `-sustain` sets secondary flag bit `5`
- `-fakePerspective` sets secondary flag bit `1`
- `-noCullFaces` sets secondary flag bit `10`

## `align`

Recovered options:

- alignment enum name as first argument
- `-damp <float>`
- `-bank <float> <float>`
- `-windBank <float> <float>`
