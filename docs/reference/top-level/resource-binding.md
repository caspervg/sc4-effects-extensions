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

## `effectGroup` / `instance`

```fx
effectGroup <groupID>
    instance <instanceID> <effectName>
end
```

## `loadResource`

```fx
loadResource <uint>
```

## `effectsResource`

```fx
effectsResource <uint> <name>
    ...
end
```
