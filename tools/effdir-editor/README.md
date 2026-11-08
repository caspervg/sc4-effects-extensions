# EFFDIR Editor

Cross-platform wxPython editor for the SimCity 4 packed `EFFDIR` resource
(`EA5118B0-EA5118B1-00000001`), built to the contract in
[`docs/reference/binary/effdir-editor-spec.md`](../../docs/reference/binary/effdir-editor-spec.md)
and [`effdir.md`](../../docs/reference/binary/effdir.md).

## Architecture

Three layers, matching the spec:

- `container/` — DBPF index parsing, QFS/RefPack decompression, and the
  `EffDirSource` adapter boundary (`DbpfEffDirSource` for `.dat` packages,
  `LocalFileEffDirSource` for a raw extracted `EFFDIR` blob). Never
  interprets EFFDIR bytes.
- `wire/` — bounded cursor, u8/u16/u32/f32/string/vector primitives,
  `Raw[T]`/`WireVector[T]`/`WireString` wrappers that keep raw bytes and
  source spans alongside decoded values.
- `model/` — one module per record type (particle, decal, shake, light,
  dynamic particle, components, effect description, top-level resource
  spine), each a `read_X`/`write_X`/`default_X` triple over the wire layer.
- `editor/` — the headless session/API (`open`/`list_nodes`/`get_node`/
  `set_raw`/`add_record`/`remove_record`/`add_effect`/`undo`/`redo`/
  `commit`) that both the UI and any future scripting entry point call.
- `bindings/` — the command-binding catalog mapping text-format command
  names to wire members, with evidence levels.
- `fx/` — the `.fx` source language in both directions. The decompiler
  (`resource.py` and its per-record emitters) turns the binary model into
  source, and every field it cannot represent is reported through a
  `Coverage` object rather than guessed. The compiler (`parser.py`, a Lark
  grammar, and `compiler.py`) turns source into the binary model and packed
  bytes.
  Constructor and command-parser defaults used for canonical minimal output
  are documented in [`docs/compiler-defaults.md`](docs/compiler-defaults.md).
  Recovered command equivalences, irrecoverable source distinctions, and
  the remaining compile differences against vanilla are documented in
  [`docs/decompiler-semantics.md`](docs/decompiler-semantics.md).
- `ui/` — wxPython AUI-docked workspace (resource tree, property-grid
  record editor, hex view with source-span highlighting, diagnostics
  list). Only talks to `editor/`, never to `wire/`/`model/` directly.

## Running

```sh
uv run effdir-editor
# or
uv run python -m effdir_editor
```

On Windows, the editor opts into per-monitor DPI awareness and scales its
custom-painted geometry with wxPython DIP units, so it remains sharp and
usable when Windows display scaling is above 100% or when the window moves
between monitors with different scale factors.

## Current scope (first version)

- Full lossless read/write round trip for major 3 and 4 resources,
  including the version-1 effect-description read profile, marker words,
  and unknown/trailing bytes.
- Add/remove particles, decals, shakes, lights, dynamic particles,
  component records, and effect descriptions (with their name-map entry).
- Raw field editing everywhere; command-binding labels/evidence shown
  where the catalog has an entry.
- The record editor has a field filter, a resizable incoming/outgoing reference
  table, and a modal line editor for scalar curve-like vectors.
- Binding-driven `set_command` transactions and per-bit flag editors.
- Optional QFS compression on DBPF writes, preserving the original state by default.
- Unsupported major versions or malformed input fall back to a
  raw-preserved, read-only resource rather than guessing a layout.
- Export decompiled `.fx` source: the whole resource (File → Export as
  .fx...), a single effect and the pools it directly references, or an
  effect plus its full transitive dependency closure (right-click an
  effect description in the tree). Each export opens a syntax-highlighted
  preview listing everything that could not be represented before you
  save or copy it.

## Compiling `.fx` source

```sh
uv run effdir-compile input.fx -o out.dat --instance 0x7ABC0001
```

This compiles `input.fx` and writes it as `EA5118B0-EA5118B1-<instance>`, the
same shape as a small plugin EFFDIR entry. If `out.dat` already exists, the
entry is added or replaced and every other entry of the package is kept. The
`--compress` switch stores the entry QFS-compressed. Bad input is reported as
`file:line: message` and the command exits with status 1. `include` and
`sinclude` lines are resolved relative to the including file, and compiling
the decompiled vanilla `EFFDIR` reproduces all 1,094,484 bytes. Third-party
files such as NAM previews and the JENX packs were written by another tool:
pass `--profile legacy-tool` to reproduce most of them byte for byte, and see
`docs/decompiler-semantics.md` for what that profile changes and what it does
not reach.

From Python, `effdir_editor.fx.compile_source(text, file="x.fx")` returns the
`EffDirResource`, and `compile_to_bytes` returns the packed bytes.

## Tests

```sh
uv run pytest
```
