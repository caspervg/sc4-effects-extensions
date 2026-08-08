"""Resource tree: structural navigation (records + collections) over an
EditorSession, lazily populated. Leaf field editing happens in the record
editor panel, not here -- see effdir-editor-spec.md's "Workspace layout".
"""

from __future__ import annotations

from typing import Callable, Optional

import wx
import wx.dataview as dv

from ..editor import api
from ..editor.session import EditorSession

_EXPANDABLE_KINDS = {"record", "collection"}


class ResourceTree(wx.Panel):
    def __init__(self, parent, on_select: Callable[[str], None]):
        super().__init__(parent)
        self._on_select = on_select
        self._session: Optional[EditorSession] = None

        self.tree = dv.TreeListCtrl(self, style=dv.TL_SINGLE)
        self.tree.AppendColumn("Node", width=220)
        self.tree.AppendColumn("Type", width=160)
        self.tree.AppendColumn("Evidence", width=90)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.tree, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.tree.Bind(dv.EVT_TREELIST_ITEM_EXPANDING, self._on_expanding)
        self.tree.Bind(dv.EVT_TREELIST_SELECTION_CHANGED, self._on_selection_changed)

    def load(self, session: EditorSession) -> None:
        self._session = session
        self.tree.DeleteAllItems()
        root = self.tree.GetRootItem()
        self._append_children(root, "")

    def refresh(self) -> None:
        if self._session is not None:
            self.load(self._session)

    def _append_children(self, parent_item, path: str) -> None:
        assert self._session is not None
        for summary in api.list_nodes(self._session, path or None):
            item = self.tree.AppendItem(parent_item, self._short_label(summary.path))
            self.tree.SetItemText(item, 1, summary.record_type)
            self.tree.SetItemText(item, 2, summary.evidence)
            self.tree.SetItemData(item, summary.path)
            kind = self._kind_of(summary.path)
            if kind in _EXPANDABLE_KINDS and self._has_children(summary.path):
                self.tree.AppendItem(item, "")  # placeholder to show the expander

    @staticmethod
    def _short_label(path: str) -> str:
        if "." in path:
            tail = path.rsplit(".", 1)[-1]
        else:
            tail = path
        return tail

    def _kind_of(self, path: str) -> str:
        from ..editor import nodes as _nodes
        from ..editor import paths as _paths

        return _nodes.classify(_paths.get_path(self._session.working, path))

    def _has_children(self, path: str) -> bool:
        assert self._session is not None
        from ..editor import nodes as _nodes

        return len(_nodes.child_paths(self._session.working, path)) > 0

    def _on_expanding(self, event: dv.TreeListEvent) -> None:
        item = event.GetItem()
        path = self.tree.GetItemData(item)
        if path is None:
            return
        first_child = self.tree.GetFirstChild(item)
        if first_child.IsOk() and self.tree.GetItemData(first_child) is None:
            self.tree.DeleteItem(first_child)
            self._append_children(item, path)

    def _on_selection_changed(self, event: dv.TreeListEvent) -> None:
        item = event.GetItem()
        path = self.tree.GetItemData(item)
        if path is not None:
            self._on_select(path)
