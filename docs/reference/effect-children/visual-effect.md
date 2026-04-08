# `visualEffect`

Status: `Confirmed`

`visualEffect` references another named top-level `effect` from inside an
`effect` block.

## Syntax

```fx
visualEffect existing_fx [shared child options...]
```

## Notes

- valid only inside `effect`
- referenced effect must already exist
- unknown names throw `Unknown visual effect: %s`
