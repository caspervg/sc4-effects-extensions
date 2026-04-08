# `light`

Status: `Confirmed`

`light` defines reusable light data used by `flashEffect` and `tintEffect`.

## Syntax

```fx
light name [: baseName]
    strength ...
    length ...
    color ...
end
```

## Recovered nested commands

- `strength <float> [<float> ...]`
- `length <float> [-fade <float>]`
- `color <colorSample...>`
- `colour <colorSample...>`
- `color255 <colorSample...>`
- `colour255 <colorSample...>`

## Important grouping rule

Each color sample should stay a single argument:

```fx
color "1.0 1.0 1.0"
color255 "255 255 255"
```
