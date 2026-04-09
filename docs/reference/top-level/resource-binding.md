# Resource binding and effect IDs

Status: `Confirmed`

These commands bind symbolic names to IDs or map effects to effect keys.

## `textureID`

```fx
textureID my_texture_name 12345678
```

## `modelID`

```fx
modelID my_model_name 12345678
```

## `soundID`

```fx
soundID my_sound_name 12345678
```

## Numeric parsing notes

These commands accept:

- decimal values
- lowercase `0x...` hex
- some simple numeric expressions supported by the shared parser

## `effectID`

```fx
effectID <groupID> <instanceID> <effectName>
```

Recovered behavior:

- requires exactly three author arguments after the command token
- lowercases the effect name before storing it
- binds an effect name to a two-part numeric key
- this feeds the collection's effect-key mapping table
- this is distinct from `messageTrigger`, which binds a message id to an
  effect name for runtime spawning

## `effectGroup` / `instance`

```fx
effectGroup <groupID>
    instance <instanceID> <effectName>
end
```

Recovered behavior:

- `effectGroup` requires one numeric id argument
- `instance` requires exactly two arguments
- the grouped form writes the same underlying effect-key mapping as `effectID`
- effect names are lowercased before storage

## `loadResource`

```fx
loadResource <uint>
```

Recovered behavior:

- imports a packed effects resource into the active effects collection
- it uses a fixed packed-effects resource key shape:
  - `Type = 0xEA5118B0`
  - `Group = 0xEA5118B1`
  - `Instance = <uint>`
- if the resource is missing, parsing throws
  `Effects resource 0x%08x not found`
- this is not an include-by-filename feature and does not parse another text
  `.fx` file

## `effectsResource`

```fx
effectsResource <uint> <name>
    ...
end
```

Recovered behavior:

- creates or opens a packed effects resource using the same fixed key shape:
  - `Type = 0xEA5118B0`
  - `Group = 0xEA5118B1`
  - `Instance = <uint>`
- the block body is parsed against a resource-backed collection target
- the block cannot be nested; nested use throws `Can't nest resource blocks`
- on block end, the resource is saved back out
- if parser-side resource saving is not enabled first, this block can parse as
  a no-op container instead of creating or saving a packed resource

## Resource-saving gate

On the recovered parser path, `effectsResource` only performs real save work
when parser-side resource saving has already been enabled.

On Windows, this is especially important:

- the parser-side save-enable call must happen before queued effects files are
  parsed
- otherwise `effectsResource::Parse` and `effectsResource::EndBlock` do not
  enter the real save path

## Windows packed-resource requirement

On Windows, enabling resource saving is necessary but not sufficient.

`effectsResource` also requires a writable persist DB segment registered for
packed-effects group `0xEA5118B1`.

Practical consequence:

- a normal loaded plugin `.dat` containing `EA5118B0:EA5118B1:<iid>` is not, by
  itself, enough to satisfy the save path
- if no matching writable segment is registered, save can fail with
  `couldn't find segment for effect group 0x%08x`

This is why packed-resource authoring should be understood as packed-resource
serialization, not as a text-file include mechanism.
