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
- this command clearly affects city/simulation state, not only visuals
