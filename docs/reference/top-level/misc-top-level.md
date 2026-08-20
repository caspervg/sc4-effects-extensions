# Camera, priority, test spawns, and message triggers

## `camera`

Status: `Confirmed`

```fx
camera <f0> [f1 f2 f3 f4] -parallax <near> <far> -size <float> -sideSwipe <float>
```

The command token is `camera`; the class behind it is `cCameraParamsCommand`
(`cSC4EffectsParser::RegisterCommands`, Mac `0x00402931`), but
`cameraParams` is not a command and is rejected with
`Unknown command 'cameraParams'`.

This is distinct from nested `cameraEffect`.

Notes:

- one or more non-switch floats are collected into the camera-parameter vector
- if only one float is provided, four more values are appended by repeatedly
  halving the previous value
- `-parallax` defaults to `100.0` and `101.0` when omitted
- `-size` defaults to `4.0` when omitted
- `-sideSwipe` defaults to `7.0` when omitted
- this writes collection-level default camera parameters, not an anonymous
  `cameraEffect`

## `setPriority`

Status: `Partial`

```fx
setPriority <name> <intPriority> [remapName]
```

Recovered behavior:

- requires at least two non-switch arguments
- stores a string key, an integer priority, and an optional remap target name
  in a parser-side remapping table
- this does not directly emit an effect definition
- the exact downstream use of the optional third string is still only partial

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
- the effect name must already exist or parsing throws `No such effect`
- default position is `(512, 100, 512)`
- a 2-value position is terrain-snapped
- a 3-value position is a full `vec3`
- `-sourceScale` controls the source transform scale and defaults to `1.0`
- `-scale` controls the main transform scale and defaults to `1.0`
- `-trans` sets a secondary translation vector
- `-speed` writes parameter selector `0` with one float
- `-target` writes parameter selector `5` with one `vec3`
- `-hard` records a hard-start transition instead of the default start mode
- this is an author-side bootstrap and debugging hook

## `messageTrigger`

Status: `Confirmed`

```fx
messageTrigger <messageID> <effectName>
```

Recovered behavior:

- requires exactly two non-switch arguments
- parses the first as a `uint` message id
- stores a message-trigger description in the active effects collection
- this later feeds the manager's runtime trigger map for `DoMessage()`
  auto-spawning
