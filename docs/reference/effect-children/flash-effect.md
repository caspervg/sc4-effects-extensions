# `flashEffect`

Status: `Confirmed`

`flashEffect` instantiates a named `light` definition as an event inside an
`effect`.

## Syntax

```fx
flashEffect <lightName>
flashEffect <lightName> -epicentre [float]
flashEffect <lightName> -epicenter [float]
```

## Notes

- valid only inside `effect`
- referenced light must exist
- unknown names throw `unknown light definition: %s`
- `-epicentre` and `-epicenter` are aliases
- default epicentre value is `1000.0`
