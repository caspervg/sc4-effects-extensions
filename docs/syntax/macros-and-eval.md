# Macros and eval

Status: `Confirmed`

The parser supports parameterized macros and deferred command parsing.

Macro parameters and variables use different substitution syntax:

- macro parameters use `%name` or `%{name}`
- variables use `$name`, `${name}`, or `$namespace:name`

## `define`, `enddef`, `create`

### Define a macro

```fx
define makeBurst "name scale"
    effect %name
        visualEffect burst_fx -scale %scale
    end
enddef
```

### Instantiate a macro

```fx
create makeBurst "big_burst 10.0"
```

Recovered behavior:

- `define` starts a named macro definition
- `enddef` ends it
- the second non-switch argument to `define` is split into the macro parameter list
- `create` substitutes arguments and executes the resulting commands
- `create` expects its third token to be a single argument string, which is then split into the actual macro arguments
- macro substitution scans for `%...`, not `$...`

Recovered hard errors:

- `Unknown definition: '%s'`
- `Wrong number of arguments`
- `Can't nest definitions!`
- `Unknown parameter: '%s'`

Practical note:

- use `$...` only for parser variables defined with `set`, `setf`, `setv3`, and related commands
- use `%...` only for macro parameters declared in the `define` header

## `eval`

```fx
eval "<command string>"
```

- takes exactly one string argument
- splits that string into arguments with the normal argument splitter
- reparses the result as exactly one command
- allows deferred command construction after substitution

Important limitation:

- `eval` reparses one command, not a full command stream
- it is suitable for commands like `visualEffect ...`, `particleEffect ...`,
  `testEffect ...`, or `create ...`
- it is not suitable for inline block definitions such as
  `effect ... end` or `particles ... end`

Good uses:

```fx
effect eval_child_demo
    eval "visualEffect burst_fx -scale 2.0"
end
```

```fx
set spawn_cmd "testEffect eval_child_demo -scale 1.5 -hard"
eval "$spawn_cmd"
```
