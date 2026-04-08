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

- marks the particle system as model-driven
- resolves one or more model names through `modelID`
- also supports:
  - `-fakePerspective`
  - `-moveEntireSlave`
  - `-slaveApplyAlpha`
  - `-applyAlpha`
  - `-modelSpeed <float>`
  - `-modelSpeedStatic <float>`
  - `-sustain`
  - `-applyLighting`
  - `-noCullFaces`

## `align`

Recovered options:

- alignment enum name as first argument
- `-damp <float>`
- `-bank <float> <float>`
- `-windBank <float> <float>`
