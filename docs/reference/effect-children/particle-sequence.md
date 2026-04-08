# `particleSequence`

Status: `Partial`

`particleSequence` is a nested `effect` block that changes how child
`particleEffect` entries are tagged.

## Syntax

```fx
particleSequence
    particleEffect system_a
    particleEffect system_b
end
```

## Current interpretation

- this is not the same thing as top-level `sequence`
- it appears to be a chaining / handoff wrapper for consecutive model-based
  particle systems
