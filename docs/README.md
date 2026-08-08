# SC4 effects syntax documentation

This directory contains reader-facing documentation for the recovered SimCity 4
effects language.

Scope:

- the effects `.fx` language itself
- author-facing command syntax
- recovered command behavior
- practical composition patterns

Out of scope here:

- the separate render-properties / rules DSL
- source mapping and reverse-engineering notebook details

Status labels used in these docs:

- `Confirmed`: directly backed by recovered parser or runtime behavior
- `Partial`: parser shape is clear, but some semantics are still uncertain
- `Inferred`: likely meaning based on naming, surrounding behavior, or runtime
  cross-checks

## Start here

- [Language overview](./syntax/overview.md)
- [Comments](./syntax/comments.md)
- [Variables](./syntax/variables.md)
- [Namespaces](./syntax/namespaces.md)
- [Macros and eval](./syntax/macros-and-eval.md)
- [Blocks and scopes](./syntax/blocks-and-scopes.md)

## Top-level definitions and commands

- [effect](./reference/top-level/effect.md)
- [particles](./reference/top-level/particles.md)
- [dynamicParticle](./reference/top-level/dynamic-particle.md)
- [decal](./reference/top-level/decal.md)
- [shake](./reference/top-level/shake.md)
- [light](./reference/top-level/light.md)
- [sequence](./reference/top-level/sequence.md)
- [Resource binding and effect IDs](./reference/top-level/resource-binding.md)
- [Camera, priority, test spawns, and message triggers](./reference/top-level/misc-top-level.md)
- [Packed EFFDIR wire format](./reference/binary/effdir.md)
- [EFFDIR editor specification](./reference/binary/effdir-editor-spec.md)

## Nested effect commands

- [Shared child options](./reference/effect-children/shared-options.md)
- [visualEffect](./reference/effect-children/visual-effect.md)
- [particleEffect](./reference/effect-children/particle-effect.md)
- [dynamicParticleEffect](./reference/effect-children/dynamic-particle-effect.md)
- [decalEffect](./reference/effect-children/decal-effect.md)
- [select](./reference/effect-children/select.md)
- [particleSequence](./reference/effect-children/particle-sequence.md)
- [soundEffect](./reference/effect-children/sound-effect.md)
- [cameraEffect](./reference/effect-children/camera-effect.md)
- [flashEffect](./reference/effect-children/flash-effect.md)
- [shakeEffect](./reference/effect-children/shake-effect.md)
- [tintEffect](./reference/effect-children/tint-effect.md)
- [chainEffect](./reference/effect-children/chain-effect.md)
- [brushEffect](./reference/effect-children/brush-effect.md)
- [scrubberEffect](./reference/effect-children/scrubber-effect.md)
- [automataEffect](./reference/effect-children/automata-effect.md)

## Particle subcommands

- [Particle overview](./reference/particles/overview.md)
- [Appearance curves](./reference/particles/appearance.md)
- [source](./reference/particles/source.md)
- [rate, inject, maintain](./reference/particles/rate-inject-maintain.md)
- [emit](./reference/particles/emit.md)
- [force](./reference/particles/force.md)
- [warp](./reference/particles/warp.md)
- [randomWalk](./reference/particles/random-walk.md)
- [collision](./reference/particles/collision.md)
- [terrainRepel](./reference/particles/terrain-repel.md)
- [texture, model, align](./reference/particles/rendering.md)
- [effectBase and timedEffect](./reference/particles/effect-base-and-timed-effect.md)
