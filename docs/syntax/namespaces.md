# Namespaces

Status: `Confirmed`

Namespaces provide scoped variable storage.

## Syntax

```fx
namespace demo
    set x 1
end
```

## Lookup

Recovered namespaced lookup form:

```fx
$demo:x
```

## Practical use

Namespaces are useful for reusable parameter sets:

```fx
namespace smoke
    setf scale 2.0
    setc color "0.7 0.7 0.7 0.8"
end
```

## Recovered behavior

- `namespace <name>` is a block command and must be closed with `end`
- entering a namespace pushes a namespace prefix onto the parser scope stack
- leaving the block pops that namespace prefix
- variables can be referenced explicitly through `$namespace:name`
- unqualified lookups still search through the active namespace stack

Practical note:

- namespaces are parser-variable scope only
- they do not create effect objects or separate definition containers by themselves
