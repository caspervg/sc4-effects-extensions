# `shakeEffect`

Status: `Confirmed`

`shakeEffect` instantiates a named `shake` definition as an event inside an
`effect`.

## Syntax

```fx
shakeEffect <shakeName>
shakeEffect <shakeName> -noEpicentre
shakeEffect <shakeName> -noEpicenter
```

## Notes

- valid only inside `effect`
- referenced shake definition must exist
- unknown names throw `Unknown shake definition: %s`
