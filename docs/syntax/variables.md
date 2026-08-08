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

The typed setter commands normalize their input before storing it in the parser
variable table. The stored value is still text, but the helper canonicalizes it
first.

- `set` stores the provided value text with no special type conversion
- `seti` parses as integer and stores canonical integer text
- `setf` parses as float and stores canonical float text
- `setc` parses color text, applies optional transforms, and stores normalized color text
- `setv3` parses vector text, applies optional transforms, and stores normalized vector text

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
- variables participate in namespace lookup, including the explicit
  `$namespace:name` form
