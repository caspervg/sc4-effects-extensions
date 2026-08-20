# Blocks and scopes

Status: `Confirmed`

The language is block-based. Grouped constructs are opened by a command and
closed with `end`.

## Named top-level definition blocks

- `effect`
- `particles`
- `dynamicParticle`
- `decal`
- `shake`
- `light`
- `sequence`

Several support inheritance with `: <baseName>`.

## Nested effect blocks

Inside `effect`, recovered nested commands include:

- `visualEffect`
- `particleEffect`
- `dynamicParticleEffect`
- `decalEffect`
- `shakeEffect`
- `flashEffect`
- `tintEffect`
- `soundEffect`
- `cameraEffect`
- `chainEffect`
- `brushEffect`
- `scrubberEffect`
- `automataEffect`
- `sequenceEffect`
- `select`
- `particleSequence`

`sequence` (top level) and `sequenceEffect` (inside `effect`) are two
different commands registered in two different tables: the first defines a
sequence, the second references one by name.

## Scope restrictions

Many commands are only valid inside a specific parent block.

Examples:

- `flashEffect` is only valid inside `effect`
- particle subcommands such as `emit` or `source` are only valid inside
  `particles`
