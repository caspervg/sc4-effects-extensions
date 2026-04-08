# `sequence`

Status: `Confirmed`

`sequence` is a top-level timing block for playing named effects in order.

## Syntax

```fx
sequence name [switches...]
    wait ...
    play ...
end
```

## Recovered switches

- `-loop`
- `-noOverlap`
- `-hardStart`

## Nested commands

### `wait`

```fx
wait a
wait a b
```

### `play`

```fx
play effectName a
play effectName a b
```
