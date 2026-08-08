# `shake`

Status: `Partial`

`shake` defines a named reusable shake description consumed by `shakeEffect`.

## Syntax

```fx
shake name [: baseName]
    length ...
    amplitude ...
    frequency ...
    shakeAspect ...
    table ...
end
```

## Recovered nested commands

- `length`
- `amplitude`
- `frequency`
- `shakeAspect`
- `table`

## Runtime behavior

- `length` is the total duration and normalizes both curves to `0..1`
- `amplitude` controls displacement magnitude over normalized time
- `frequency` advances the phase through a 64-sample displacement table
- `shakeAspect` scales X by its reciprocal and Y by the value itself
- `table random` selects a deterministic two-axis random table
- `table sineY` selects a vertical sine wave with zero horizontal samples
- a positioned `shakeEffect` uses radial squared-distance attenuation
- lower zoom levels attenuate the combined shake by `0.6` per level below 4

`length -fade <seconds>` defines the tail used when an active shake is
stopped early. A nonzero fade moves playback to `length - fade`; it does not
create an independent fade curve. A zero fade removes the shake immediately.

Runtime evidence is confirmed in both the symbolized Mac build
(`cSC43DRender::SetShakeOffsets`, `0x00507A20`) and Windows 1.1.641
(`0x007C86D0`).
