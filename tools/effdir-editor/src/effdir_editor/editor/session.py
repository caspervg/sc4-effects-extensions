"""EditorSession: undo/redo via full-resource snapshots and a change log
for display (effdir-editor-spec.md, "UI state and transactions"). No wx
dependency -- this is the layer both the UI and headless agents share.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, List, Optional, Set

from ..container.adapter import EffDirSource, ResourceHandle
from ..model.resource import EffDirResource, read_resource


@dataclass
class Change:
    path: str
    before: Any
    after: Any
    reason: str  # "user" | "binding" | "allocation" | "repair"
    warnings: List[str] = field(default_factory=list)


@dataclass
class ChangeSet:
    changes: List[Change]
    diagnostics: List[Any]


@dataclass
class SessionState:
    """One coherent undo/redo point, including its visible change history."""

    working: EffDirResource
    change_log: List[Change]


@dataclass
class EditorSession:
    handle: ResourceHandle
    source: EffDirSource
    original_bytes: bytes
    working: EffDirResource
    undo_stack: List[SessionState] = field(default_factory=list)
    redo_stack: List[SessionState] = field(default_factory=list)
    change_log: List[Change] = field(default_factory=list)
    selected_path: Optional[str] = None

    @property
    def dirty(self) -> bool:
        return bool(self.undo_stack)

    @property
    def dirty_paths(self) -> Set[str]:
        return {c.path for c in self.change_log}

    @property
    def new_paths(self) -> Set[str]:
        """Paths allocated during the current, uncommitted edit session."""

        return {c.path for c in self.change_log if c.reason == "allocation" and c.after is not None}

    def snapshot(self) -> None:
        self.undo_stack.append(
            SessionState(
                working=copy.deepcopy(self.working),
                change_log=copy.deepcopy(self.change_log),
            )
        )
        self.redo_stack.clear()

    def record_change(self, path: str, before: Any, after: Any, reason: str = "user", warnings=None) -> Change:
        change = Change(path=path, before=before, after=after, reason=reason, warnings=warnings or [])
        self.change_log.append(change)
        return change

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append(SessionState(working=self.working, change_log=self.change_log))
        state = self.undo_stack.pop()
        self.working = state.working
        self.change_log = state.change_log

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append(SessionState(working=self.working, change_log=self.change_log))
        state = self.redo_stack.pop()
        self.working = state.working
        self.change_log = state.change_log


def open_session(source: EffDirSource, handle: ResourceHandle) -> EditorSession:
    data = source.read(handle)
    resource = read_resource(data)
    return EditorSession(handle=handle, source=source, original_bytes=data, working=resource)
