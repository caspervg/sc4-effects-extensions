"""Recursive substring search over the resource tree, for the UI's filter
box. Case-insensitive match against a node's path, its display_name (see
references.py/nodes.py), and its record type -- the same three things the
resource tree already shows per row, so "what you can see, you can find".

Walks live values via `iter_child_values` rather than `build_node`/
`child_paths`'s path-string API: those re-walk from the resource root on
every call, which is fine for the handful of calls the tree/record editor
make per user action, but turns O(n) into O(n^2) over a full recursive
walk of a large resource (the real vanilla EFFDIR has tens of thousands of
leaf fields once every particle/decal/effect record is counted).
"""

from __future__ import annotations

from typing import List

from .nodes import NodeSummary, classify, iter_child_values, resolve_display_name, resolve_record_type
from .references import ReferenceIndex

# Bounds worst-case latency on a query with zero/rare matches over a large
# resource.
_VISIT_BUDGET = 200_000


def find_nodes(root, reference_index: ReferenceIndex, query: str, *, limit: int = 200) -> List[NodeSummary]:
    query = query.strip().lower()
    if not query:
        return []
    results: List[NodeSummary] = []
    _walk(root, "", reference_index, query, results, limit, [_VISIT_BUDGET])
    return results


def _walk(value, path: str, reference_index, query: str, results: List[NodeSummary], limit: int, budget: List[int]) -> None:
    for suffix, child_value in iter_child_values(value):
        if len(results) >= limit or budget[0] <= 0:
            return
        budget[0] -= 1
        child_path = f"{path}{suffix}" if suffix.startswith("[") else (f"{path}.{suffix}" if path else suffix)
        display_name = resolve_display_name(child_value, child_path, reference_index)
        record_type = resolve_record_type(classify(child_value), child_value)
        haystack = f"{child_path} {record_type} {display_name or ''}".lower()
        if query in haystack:
            results.append(
                NodeSummary(
                    path=child_path,
                    record_type=record_type,
                    label=None,
                    evidence="wire",
                    dirty=False,
                    display_name=display_name,
                )
            )
        _walk(child_value, child_path, reference_index, query, results, limit, budget)
