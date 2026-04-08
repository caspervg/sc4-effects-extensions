# `decalEffect`

Status: `Confirmed`

`decalEffect` references a named top-level `decal` definition inside an
`effect`.

## Syntax

```fx
decalEffect ExistingDecalName [shared child options...]
```

## Notes

- valid only inside `effect`
- referenced decal definition must exist
- unknown names throw `Unknown decal definition: %s`
