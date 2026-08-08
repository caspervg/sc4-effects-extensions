# Macros and eval

Status: `Confirmed`

The parser supports parameterized macros, repeated macro instantiation, and
deferred command parsing.

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
- while a definition is open, subsequent commands are recorded instead of executed
- `enddef` ends it and registers the definition by name
- the second non-switch argument to `define` is split into the macro parameter list
- `create` substitutes arguments and executes the resulting commands
- `create` expects its third token to be a single argument string, which is then split into the actual macro arguments
- macro substitution scans for `%...`, not `$...`

Recovered hard errors:

- `Unknown definition: '%s'`
- `Wrong number of arguments`
- `Can't nest definitions!`
- `Found enddef without matching define`
- `Unknown parameter: '%s'`

Practical note:

- use `$...` only for parser variables defined with `set`, `setf`, `setv3`, and related commands
- use `%...` only for macro parameters declared in the `define` header

## `arrayCreate`

```fx
arrayCreate makeBurst 4
```

Recovered behavior:

- takes exactly two arguments after the command name:
  the macro definition name and an integer count
- expands internally into repeated `create` calls
- each iteration behaves like:
  `create <definition> "<index> <count>"`
- the first generated macro argument is the zero-based loop index
- the second generated macro argument is the total iteration count

Practical interpretation:

- `arrayCreate` is the closest thing this DSL has to a loop helper
- it does not execute an arbitrary command body directly
- it only repeats a previously defined macro

Example:

```fx
define makeBurst "i count"
    effect burst_%i
        visualEffect burst_fx -scale %count
    end
enddef

arrayCreate makeBurst 3
```

This expands as if the parser had executed:

```fx
create makeBurst "0 3"
create makeBurst "1 3"
create makeBurst "2 3"
```

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

## Parser utility stubs

These names are registered by the shared parser layer, but not all of them are
useful in this MacSC4 binary:

- `list` is registered but throws `unimplemented`
- `trace` is registered, requires exactly one argument after the command name,
  and otherwise appears to have no effect in this build
