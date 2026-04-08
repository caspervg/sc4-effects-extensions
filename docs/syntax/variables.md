# Variables

Status: `Confirmed`

The parser supports named variables and several typed setter forms.

## Defining variables

```fx
set myVar hello
seti myInt 42
setf myFloat 3.14
setc myColor "1 0.5 0.25 0.8"
setv3 myVec "1 2 3"
```

Recovered setter families:

- `set`
- `seti`
- `setf`
- `setc`
- `setv3`

## Referencing variables

Recovered forms:

```fx
$myVar
${myVar}
$demo:myVar
```

Missing variables are hard errors:

```text
Unknown variable: '%s'
```

## Typed helpers

### `setc`

Recovered parse-time helpers:

- `-scale <float>`
- `-mult <color>`
- `-add <color>`
- `-alpha <float>`

### `setv3`

Recovered parse-time helpers:

- `-scale <float>`
- `-mult <vec3>`
- `-add <vec3>`

## Practical notes

- variable substitution is part of normal parsing
- typed setters let you precompute reusable constants in the file itself
- vector- and color-like values are safest when grouped into one quoted argument
