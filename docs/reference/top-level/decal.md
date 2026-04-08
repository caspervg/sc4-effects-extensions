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

## Notes

- inheritance is supported
- color samples should be grouped, for example `"1.0 0.8 0.3"`
- `texture` resolves symbolic names through `textureID`
