# `decal`

Status: `Confirmed`

`decal` defines a named reusable decal description.

## Syntax

```fx
decal name [: baseName]
    color ...
    alpha ...
    size ...
    aspect ...
    rotate ...
    life ...
    texture ...
end
```

## Recovered nested commands

- `color`
- `color255`
- `colour`
- `colour255`
- `alpha`
- `alpha255`
- `size`
- `aspect`
- `rotate`
- `life`
- `texture`

## `draw`

The draw enum is a switch on `texture`, not a nested command of its own:

```fx
texture my_texture -light -draw decalInvertDepth
```

The parser rejects a bare `draw <mode>` line with `unknown command draw`:
`cDecalTextureCommand::Parse` (Mac `0x00785890`) reads `draw` as a switch on
`texture`.

Decals have their own five-value enum table (`kDecalDrawTypes`, Mac
`0x00abaf60`) -- **not** the eight-value particle table. Using a particle name
here throws `Unknown enum '%s'`.

| Value | Name |
| ---: | --- |
| 0 | `decal` |
| 1 | `additive` |
| 2 | `modulate` |
| 3 | `decalInvertDepth` |
| 4 | `decalNoOverlap` |

## Notes

- inheritance is supported
- color samples should be grouped, for example `"1.0 0.8 0.3"`
- `texture` resolves symbolic names through `textureID`; it does not accept a
  raw numeric key, and an unbound name throws `No such texture: '%s'`
