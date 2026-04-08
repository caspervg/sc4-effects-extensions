# `brushEffect`

Status: `Confirmed`

Anonymous brush component inside an `effect`.

## Syntax

```fx
brushEffect
    -name <brushName>
    -rate <float>
    -apply <float>
    -length <float>
    -zoom <1..5>
    -strength <min> [max]
    -width <min> [max]
    -level <float>
```

## Notes

- `-name` is required
- unknown names throw `No such brush: '%s'`
- `-zoom` is stored zero-based internally
