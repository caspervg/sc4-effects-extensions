"""Dotted/bracket path resolution over the EFFDIR resource model, e.g.
"particles[3].life" or "components.brushes[0].key".
"""

from __future__ import annotations

import re
from typing import Any, List, Tuple, Union

from ..wire import WireVector

PathToken = Union[str, int]

_TOKEN_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]")


def tokenize(path: str) -> List[PathToken]:
    tokens: List[PathToken] = []
    for m in _TOKEN_RE.finditer(path):
        name, idx = m.groups()
        tokens.append(name if name is not None else int(idx))
    return tokens


def format_tokens(tokens: List[PathToken]) -> str:
    if not tokens:
        return ""
    out = str(tokens[0])
    for tok in tokens[1:]:
        out += f"[{tok}]" if isinstance(tok, int) else f".{tok}"
    return out


def parent_path(path: str) -> str:
    return format_tokens(tokenize(path)[:-1])


def _get_item(container: Any, key: PathToken) -> Any:
    if isinstance(key, int):
        return container.items[key] if isinstance(container, WireVector) else container[key]
    return getattr(container, key)


def _set_item(container: Any, key: PathToken, value: Any) -> None:
    if isinstance(key, int):
        if isinstance(container, WireVector):
            container.items[key] = value
        else:
            container[key] = value
    else:
        setattr(container, key, value)


def get_path(root: Any, path: str) -> Any:
    obj = root
    for tok in tokenize(path):
        obj = _get_item(obj, tok)
    return obj


def get_parent_and_key(root: Any, path: str) -> Tuple[Any, PathToken]:
    tokens = tokenize(path)
    if not tokens:
        raise ValueError("empty path has no parent")
    obj = root
    for tok in tokens[:-1]:
        obj = _get_item(obj, tok)
    return obj, tokens[-1]


def set_path(root: Any, path: str, value: Any) -> None:
    parent, key = get_parent_and_key(root, path)
    _set_item(parent, key, value)
