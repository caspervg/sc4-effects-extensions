# `scrubberEffect`

Status: `Confirmed`

Anonymous scrubber component inside an `effect`.

## Supported options

- `-demolish <float>`
- `-burn <float>`
- `-toxic <float>`
- `-extinguishFire <uint>`
- `-pauseSim [float]`
- `-pauseSimHidden [float]`
- `-pauseClock [float]`
- `-message <uint> [uint]`
- `-blob <1..8> <float> <float> [float]`
- `-rect <1..8> <float> <float> <float> [float]`
- `-noNetworks`
- `-noFlora`
- `-dezone`
- `-single`
- `-explode`
- `-createRubble`
- `-createBurntRubble`
- `-demolishEffectID <uint>`
- `-minDemolishSize <float>`
- `-maxDemolishSize <float>`

## Notes

- if no meaningful options are supplied, parsing throws
  `Need some options for anonymous scrubber effect`
- `-demolish`, `-burn`, and `-toxic` clamp negative values to `0`
- `-message <uint> [uint]` stores one required message id and one optional
  trailing parameter
- `-blob <1..8> <float> <float> [float]` stores a bounded shape selector plus
  two required floats and an optional fourth float; if the fourth value is
  omitted, one dimension is mirrored
- `-rect <1..8> <float> <float> <float> [float]` stores a bounded shape
  selector plus three required floats and an optional fourth float
- pause-related switches accept an optional duration float
- demolition-related switches pack several mode bits and an effect-ID byte into
  one stored field
- `demolishEffect`, `gameEffect`, and `mapEffect` are registered through this
  same parser implementation and likely share most or all of this switch
  surface
- this command clearly affects city/simulation state, not only visuals
