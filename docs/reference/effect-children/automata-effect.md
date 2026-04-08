# `automataEffect`

Status: `Confirmed`

Anonymous automata / attractor-style component inside an `effect`.

## Syntax

```fx
automataEffect
    -name <string>
    -group <string>
```

## Notes

- at least one of `-name` or `-group` is required
- missing both throws:
  `Need at least -name or -group for anonymous attractor effect`
