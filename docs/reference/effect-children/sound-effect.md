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
- non-switch positional arguments are not supported in this anonymous form and
  throw `sound description unimplemented`
- missing `-name` throws `Need at least -name for anonymous soundEffect`
- sound names are lowercased before lookup
- `-locationUpdateRate <x>` stores `1.0 / x` when `x > 0`
- `-length <float>` sets an explicit sound-effect length
- unknown names throw `Unknown sound %s`
