# Camera, priority, test spawns, and message triggers

## `camera`

Status: `Confirmed`

```fx
camera <f0> [f1 f2 f3 f4]
    -parallax <near> <far>
    -size <float>
    -sideSwipe <float>
```

This is distinct from nested `cameraEffect`.

## `setPriority`

Status: `Partial`

```fx
setPriority <name> <intPriority> [remapName]
```

## `testEffect`

Status: `Confirmed`

```fx
testEffect ExistingEffectName [pos2_or_pos3]
    -sourceScale <float>
    -scale <float>
    -trans <vec3>
    -speed <float>
    -target <vec3>
    -hard
```

Notes:

- creates an effect during parse/load
- default position is `(512, 100, 512)`
- a 2-value position is terrain-snapped
- a 3-value position is a full `vec3`

## `messageTrigger`

Status: `Confirmed`

```fx
messageTrigger <messageID> <effectName>
```
