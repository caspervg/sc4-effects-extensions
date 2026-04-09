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
- brush lookup is case-insensitive
- the parser first tries the lowercased brush name directly, then a
  synthesized fallback name before failing
- unknown names throw `No such brush: '%s'`
- `-apply` writes the same numeric field as `-rate` and also enables an
  internal apply-mode flag
- `-zoom` is stored zero-based internally
- this path is added as a non-one-shot anonymous description, unlike
  one-shot-style component families such as `cameraEffect`
