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
- the parser builds the definition in a scratch `cSC4EffectDescription` and
  commits it when the block closes
- the top-level effect switches map to bits in a recovered 9-bit-style flag
  word
- `-priority <1..5>` writes the effect priority field directly
- `-startMessage <u32> <u32> <u32>` stores three trailing message values in the
  effect description itself
- `-startMessage` is distinct from top-level `messageTrigger`
- `messageTrigger` binds a runtime message id to an effect name for manager-side
  auto-spawning, while `-startMessage` is serialized as part of the effect
  definition record
