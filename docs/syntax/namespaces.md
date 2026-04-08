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
