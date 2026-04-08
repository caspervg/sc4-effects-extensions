# `randomWalk`

Status: `Confirmed`

`randomWalk` enables random-walk motion shaping for particles.

## Syntax

```fx
randomWalk [options...]
```

## Recovered options

- `-delay <base> [vary]`
- `-strength <base> [vary]`
- `-turn <0..1> [0..1]`
- `-wait`
- `-preferSea`
- `-preferDir <vec3>`

## Notes

- command presence alone enables random-walk behavior
- `-delay` and `-strength` use a base-plus-variation pattern
- `-turn` uses normalized `0..1` values
