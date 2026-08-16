"""EFFDIR -> fx decompiler.

A one-way, best-effort emitter from the editor's binary resource model
to the recovered `.fx` source language (see `docs/reference/` and
`docs/syntax/`). It is not a compiler: there is no path back from fx
text to EFFDIR bytes here, and the emitted text is a re-flattened,
semantically-equivalent reconstruction rather than a recovery of
whatever an original author typed (compilation discards comments,
macros, variables, and namespaces before anything reaches the wire
format -- see the module docstrings in this package for exactly which
fields lose additional information on the way back out, and why).

Public API:

    emit_resource(resource) -> FxEmitResult
        Decompile an entire EffDirResource into one fx document.

    emit_effect_closure(resource, effect_index) -> FxEmitResult | None
        Decompile one effect plus the named pools it actually reaches.

Both return an `FxEmitResult(text, coverage)`; `coverage` is a
`Coverage` (see coverage.py) recording, for every field this package
knows how to consider, whether it was represented in `text` and why not
when it wasn't.
"""

from __future__ import annotations

from .coverage import Coverage, CoverageNote, FxEmitResult
from .resource import emit_effect_closure, emit_resource

__all__ = [
    "Coverage",
    "CoverageNote",
    "FxEmitResult",
    "emit_resource",
    "emit_effect_closure",
]
