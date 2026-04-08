# Macros and eval

Status: `Confirmed`

The parser supports parameterized macros and deferred command parsing.

## `define`, `enddef`, `create`

### Define a macro

```fx
define makeBurst "name scale"
    effect $name
        visualEffect burst_fx -scale $scale
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
- `create` substitutes arguments and executes the resulting commands

Recovered hard errors:

- `Unknown definition: '%s'`
- `Wrong number of arguments`
- `Can't nest definitions!`

## `eval`

```fx
eval "<command string>"
```

- reparses the supplied string as a command
- allows deferred command construction after substitution
