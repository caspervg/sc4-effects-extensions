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

## Runtime behavior

`length` normalizes the color and strength curves to `0..1`.
`tintEffect` sends the sampled color and strength to the lighting manager and
resets the tint after the duration. `flashEffect` draws the sampled color as a
screen overlay: positive strength uses the normal flash state with alpha
clamped to `1.0`, while negative strength selects the subtractive state and
uses its absolute value as alpha.

An epicentered flash uses squared-distance radial attenuation and is discarded
outside its radius. It is also attenuated by `0.6` per zoom step below level
4.

Although the parser accepts `length <float> -fade <float>`, `-fade` is not a
light field in this build. The handler accidentally writes it into the shake
working descriptor, so it is not serialized in `cSC4LightDescription` and
does not affect tint or flash playback.
