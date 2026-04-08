# `cameraEffect`

Status: `Confirmed`

Anonymous camera component inside an `effect`.

## Syntax

```fx
cameraEffect
    -zoom <1..5>
    -rotation <0..3>
    -attachRadius <float>
    -target
    -slave
```

## Notes

- `-zoom` is stored zero-based internally
- `-rotation` is bounded to `0..3`
