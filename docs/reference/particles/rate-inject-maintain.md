# `rate`, `inject`, and `maintain`

Status: `Confirmed`

These particle commands share a common timing/control helper.

## Shared timing options

- `-loop <float> [uint]`
- `-single [float]`
- `-sustain`
- `-scale`
- `-areaScale`
- `-volumeScale`
- `-delay <floatRange>`
- `-trigger <floatRange>`
- `-retrigger <floatRange>`

## `rate`

```fx
rate <float...> [shared timing options...]
```

## `inject`

```fx
inject <float> [shared timing options...]
```

## `maintain`

```fx
maintain <float> [timing options...]
```
