"""EFFDIR <-> fx source.

`emit_*` decompile the binary resource model to the recovered `.fx` source
language (see `docs/reference/` and `docs/syntax/`). `compile_source` and
`compile_to_bytes` compile `.fx` text back to a resource, validated against
vanilla (`docs/decompiler-semantics.md`). Decompiled text is a re-flattened
reconstruction rather than a recovery of what an author typed, since
compilation discards comments, macros, variables, and namespaces before
anything reaches the wire format. See the module docstrings for what is
lost and why.

Public API:

    emit_resource(resource) -> FxEmitResult
        Decompile an entire EffDirResource into one fx document.

    emit_effect_closure(resource, effect_index) -> FxEmitResult | None
        Decompile one effect plus the named pools it actually reaches.

    emit_descriptor(resource, path) -> FxEmitResult | None
        Decompile the single record at `path` on its own, for a live,
        per-selection preview. See PREVIEWABLE_COLLECTIONS for which
        collections have a standalone fx spelling.

Both return an `FxEmitResult(text, coverage)`; `coverage` is a
`Coverage` (see coverage.py) recording, for every field this package
knows how to consider, whether it was represented in `text` and why not
when it wasn't.
"""

from __future__ import annotations

from .coverage import Coverage, CoverageNote, FxEmitResult
from .compiler import compile_source, compile_to_bytes
from .parser import FxError
from .profiles import GAME, LEGACY_TOOL, MATLAB_2012, PROFILES, CompilerProfile
from .resource import PREVIEWABLE_COLLECTIONS, emit_descriptor, emit_effect_closure, emit_resource

__all__ = [
    "Coverage",
    "CoverageNote",
    "FxEmitResult",
    "CompilerProfile",
    "FxError",
    "GAME",
    "LEGACY_TOOL",
    "MATLAB_2012",
    "PROFILES",
    "compile_source",
    "compile_to_bytes",
    "PREVIEWABLE_COLLECTIONS",
    "emit_resource",
    "emit_effect_closure",
    "emit_descriptor",
]
