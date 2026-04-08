# Shared child options

Status: `Confirmed`

Several nested effect child commands use the same shared description-record
switches.

## Recovered shared switches

- `-offset <vec3>`
- `-rotateX <float>`
- `-rotateY <float>`
- `-rotateZ <float>`
- `-rotateXYZ <x> <y> <z>`
- `-rotateZXY <z> <x> <y>`
- `-scale <float>`
- `-lod <uint>`
- `-lodRange <min> <max>`
- `-emitScale <min> [max]`
- `-sizeScale <min> [max]`
- `-ignoreLength`
- `-respectLength`

## `select`-only support

- `-prob <float>`

Restrictions:

- `-prob` is only valid inside `select`
- `-lod` and `-lodRange` are rejected inside `select`
