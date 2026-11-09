# `collide`

Status: `Confirmed`

`collide` enables particle collision behavior. It is registered as
`collide`, and a `collision` line is rejected with `Unknown command`.

## Syntax

```fx
collide [options...]
```

## Recovered options

- `-bounce <float>`
- `-sticky`
- `-killOutsideCity`
- `-effect <float>`
- `-death <0..1>`
- `-deathByWater <0..1>`
- `-destroyBuildings`

## Notes

- valid only inside `particles`
- `collide` defaults `bounce` to `0.3` when not explicitly provided
