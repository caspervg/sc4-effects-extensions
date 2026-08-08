# Language overview

The SC4 effects language is a command-and-block DSL used to define reusable
effects and their subcomponents.

It is not just a static data file format. The recovered syntax supports:

- named top-level definitions
- nested effect composition
- typed variables
- namespaces
- macros
- loop-style macro expansion with `arrayCreate`
- deferred parsing with `eval`

The parser distinguishes between:

- variables, substituted with `$...`
- macro parameters, substituted with `%...`

It is still not a general scripting language. No conditionals or recursion have
been recovered. The closest thing to a loop is `arrayCreate`, which repeatedly
instantiates a named macro with generated `index` and `count` arguments.

## Main top-level families

The core top-level authoring commands currently documented here are:

- `effect`
- `particles`
- `dynamicParticle`
- `decal`
- `shake`
- `light`
- `sequence`

There are also top-level utility commands for:

- binding symbolic names to IDs
- camera defaults
- effect priority remapping
- message-triggered spawning
- test spawning during parse/load

## General shape

Most definitions use the same overall pattern:

```fx
definitionType name
    nestedCommand ...
    nestedCommand ...
end
```

Several top-level definition blocks also support inheritance:

```fx
particles child_name : base_name
    ...
end
```

## Practical model

The authoring flow is usually:

1. Define reusable named building blocks such as `particles`, `decal`, `light`,
   or `shake`.
2. Compose them inside a named `effect`.
3. Instantiate or trigger the final effect through the game, `testEffect`, or a
   message-trigger mapping.
