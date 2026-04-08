# `source`

Status: `Confirmed`

`source` defines the particle spawn domain and placement filters.

## Syntax

```fx
source [shape/options...]
```

## Geometric source shapes

- `-point [vec3]`
- `-square <float> [vec3]`
- `-quad <vec2> [vec3]`
- `-cube <float> [vec3]`
- `-box <vec3> [vec3]`

## Special source modes

- `-dice <float>`
- `-model`
- `-modelBase`
- `-city [min [max]]`
- `-cityWindySide [min [max]]`

## Placement and filtering options

- `-scaleParticles`
- `-pinToTerrain`
- `-pinToWater`
- `-terrainOnly`
- `-waterOnly`
- `-seaOnly`
- `-lakeOnly`
- `-belowHeight <float>`
- `-aboveHeight <float>`
- `-heightRange <min> <max>`
- `-killOutsideCity`
- `-resetIncoming`
