# `dynamicParticle`

Status: `Confirmed`

`dynamicParticle` defines a named dynamic-particle description.

## Syntax

```fx
dynamicParticle name [: baseName]
    effectBase ...
    model ...
    mass ...
    friction ...
end
```

## Recovered nested commands

- `effectBase`
- `model`
- `mass`
- `friction`

## `model` inside `dynamicParticle`

Recovered syntax:

```fx
dynamicParticle name
    model <modelName> [moreModelNames...]
end
```

Recovered behavior:

- only valid inside a `dynamicParticle` block
- resolves all non-switch arguments through the parser's `modelID` map
- model lookup is case-insensitive
- unknown names throw:
  `No such model: '%s'`
- if exactly one model name is supplied:
  - stores it directly at `+0x354`
  - clears the multi-model vector at `+0x358`
- if more than one model name is supplied:
  - stores them into the vector at `+0x358`

Unlike normal particle `model`, the recovered dynamic-particle `model` parser
does not expose draw-mode or lighting switches. It is currently just a
model-resource selection command.

## Example

```fx
dynamicParticle tumbling_debris
    effectBase debris_fx
    model spark_model
    mass 2.5
    friction 0.15 0.05 -angular 0.2
end
```
