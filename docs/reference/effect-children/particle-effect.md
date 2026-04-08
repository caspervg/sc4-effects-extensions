# `particleEffect`

Status: `Confirmed`

`particleEffect` references a named top-level `particles` definition inside an
`effect`.

## Syntax

```fx
particleEffect ExistingParticleName [shared child options...]
particleEffect ExistingParticleName -shells <count> [float]
```

## Notes

- valid only inside `effect`
- referenced particle definition must exist
- unknown names throw `Unknown particle definition: %s`
- `-shells` is recovered, but the exact meaning of its optional second value is
  still unresolved
