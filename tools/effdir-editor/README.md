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
- `ui/` — wxPython AUI-docked workspace (resource tree, property-grid
  record editor, hex view with source-span highlighting, diagnostics
  list). Only talks to `editor/`, never to `wire/`/`model/` directly.

## Running

```sh
uv run effdir-editor
# or
uv run python -m effdir_editor
```

## Current scope (first version)

- Full lossless read/write round trip for major 3 and 4 resources,
  including the version-1 effect-description read profile, marker words,
  and unknown/trailing bytes.
- Add/remove particles, decals, shakes, lights, dynamic particles,
  component records, and effect descriptions (with their name-map entry).
- Raw field editing everywhere; command-binding labels/evidence shown
  where the catalog has an entry.
- Unsupported major versions or malformed input fall back to a
  raw-preserved, read-only resource rather than guessing a layout.

Not yet implemented: `set_command` (binding-driven multi-member/bit
writes — raw editing covers this for now), QFS *compression* on write
(saved entries are stored uncompressed in the DBPF), and per-bit
flag editors.

## Tests

```sh
uv run pytest
```
