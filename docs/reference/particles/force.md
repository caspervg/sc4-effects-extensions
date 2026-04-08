# `force`

Status: `Confirmed`

`force` configures persistent forces and several specialized shaping systems.

## Simple force options

- `-reset`
- `-gravity <float>`
- `-wind <vec3> [float]`
- `-global_wind <float>`
- `-drag <float>`
- `-screw <float>`
- `-bomb <float> [vec3]`

## Attractor family

- `-attractor <float> <float...>`
- `-alphaAttractor <float> <float...>`
- `-motherDuck <float> <float...>`
- `-automata <uint> <float>`

## Tractor / path family

- `-tractor <vec3> <float|vec3> [float]`
- `-tractorRel <vec3> <float|vec3> [float]`
- `-tractorResetSpeed <float>`
- `-tractorTimeScale <float>`

## Terrain / explosion shaping

- `-terrainRepel <float> <float> [float]`
- `-explosion <float> <float...>`
- `-explosionFront <float> <float>`
