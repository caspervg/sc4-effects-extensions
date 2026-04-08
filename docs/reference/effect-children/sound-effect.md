# `soundEffect`

Status: `Confirmed`

Anonymous sound component inside an `effect`.

## Syntax

```fx
soundEffect
    -name <soundName>
    -locationUpdateRate <float>
    -length <float>
```

## Notes

- `-name` is required
- missing `-name` throws `Need at least -name for anonymous soundEffect`
- unknown names throw `Unknown sound %s`
