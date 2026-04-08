# `effect`

Status: `Confirmed`

`effect` defines a named composite visual effect.

## Syntax

```fx
effect effectName [switches...]
    childCommand ...
    childCommand ...
end
```

## Recovered switches

- `viewRelative`
- `noAutoStop`
- `hardStop`
- `rigid`
- `noPropagate`
- `applyCursor`
- `ignoreOrientation`
- `noLODStop`
- `manualRestart`
- `-startMessage <u32> <u32> <u32>`
- `-priority <1..5>`

## Notes

- nested `effect` blocks are rejected
- child components are accumulated and committed on `end`
