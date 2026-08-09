# `particleEffect`

Status: `Confirmed`

`particleEffect` references a named top-level `particles` definition inside an
`effect`.

## Syntax

```fx
particleEffect ExistingParticleName [shared child options...]
particleEffect ExistingParticleName -shells <count> [offset]
```

## Notes

- valid only inside `effect`
- referenced particle definition must exist
- unknown names throw `Unknown particle definition: %s`
- the optional second `-shells` value is stored as a rounded `u16`
- shell `i` receives `offset * i` through runtime parameter `0x101`
- the value is a spatial offset along the geometry-sourced particle view
  direction, with no time-unit conversion
- normal and model-based particle paths ignore parameter `0x101`
