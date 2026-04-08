# `particles`

Status: `Confirmed`

`particles` defines a named reusable particle system description.

## Syntax

```fx
particles name [: baseName]
    particleSubcommand ...
end
```

## Main subcommand families

- appearance curves
- source and emission
- force and motion shaping
- rendering
- collisions and terrain interaction
- timed child-effect triggers

See the dedicated particle pages in `docs/reference/particles/`.

## Notes

- inheritance is supported with `: <baseName>`
- missing names throw `No name specified!`
