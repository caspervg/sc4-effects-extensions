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

## Example

```fx
dynamicParticle tumbling_debris
    effectBase debris_fx
    model spark_model
    mass 2.5
    friction 0.15 0.05 -angular 0.2
end
```
