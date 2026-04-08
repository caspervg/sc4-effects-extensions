# `collision`

Status: `Confirmed`

`collision` enables particle collision behavior.

## Syntax

```fx
collision [options...]
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
- collision defaults `bounce` to `0.3` when not explicitly provided
