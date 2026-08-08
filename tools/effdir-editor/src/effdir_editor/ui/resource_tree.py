"""Resource tree: structural navigation (records + collections) over an
EditorSession, lazily populated. Leaf field editing happens in the record
editor panel, not here -- see effdir-editor-spec.md's "Workspace layout".

A search box above the tree filters by substring match against path,
display name, and record type (editor/search.py), then reveals and
selects matches on Enter -- the tree stays lazily populated (no need to
force-expand the whole resource), so revealing a match expands only its
ancestor chain.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import wx
import wx.dataview as dv

from ..editor import api
from ..editor import paths as _paths
from ..editor.references import build_reference_index
from ..editor.search import find_nodes
from ..editor.session import EditorSession

_EXPANDABLE_KINDS = {"record", "collection"}
_SEARCH_DEBOUNCE_MS = 200


class ResourceTree(wx.Panel):
    def __init__(self, parent, on_select: Callable[[str], None]):
        super().__init__(parent)
        self._on_select = on_select
        self._session: Optional[EditorSession] = None
        self._search_results: List[str] = []
        self._search_cursor = -1
        self._search_timer: Optional[wx.CallLater] = None
        self._suppress_selection = False

        self.search = wx.SearchCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search.SetDescriptiveText("Filter (Enter for next match)")
        self.search.ShowCancelButton(True)
        self.search_status = wx.StaticText(self, label="")
        self.search_status.SetFont(self.search_status.GetFont().Smaller())

        self.tree = dv.TreeListCtrl(self, style=dv.TL_SINGLE)
        self.tree.AppendColumn("Node", width=self.FromDIP(440))
        self.tree.AppendColumn("Type", width=160)
        self.tree.AppendColumn("Evidence", width=90)
        self.tree.AppendColumn("Refs", width=50)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.search, 0, wx.EXPAND | wx.ALL, 4)
        sizer.Add(self.search_status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)
        sizer.Add(self.tree, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.tree.Bind(dv.EVT_TREELIST_ITEM_EXPANDING, self._on_expanding)
        self.tree.Bind(dv.EVT_TREELIST_SELECTION_CHANGED, self._on_selection_changed)
        self.search.Bind(wx.EVT_TEXT, self._on_search_text)
        self.search.Bind(wx.EVT_TEXT_ENTER, self._on_search_next)
        self.search.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_search_cancel)
        self.search.Bind(wx.EVT_SEARCHCTRL_SEARCH_BTN, self._on_search_next)

    def load(self, session: EditorSession) -> None:
        self._session = session
        self.search.ChangeValue("")
        self._reset_search()
        self._rebuild()

    def _rebuild(self) -> None:
        self.tree.DeleteAllItems()
        root = self.tree.GetRootItem()
        self._append_children(root, "")

    def refresh(self) -> None:
        if self._session is None:
            return

        expanded_paths = self._expanded_paths()
        selected_item = self.tree.GetSelection()
        selected_path = self.tree.GetItemData(selected_item) if selected_item.IsOk() else None
        scroll_pos = self.tree.GetScrollPos(wx.VERTICAL)
        current_match = (
            self._search_results[self._search_cursor]
            if 0 <= self._search_cursor < len(self._search_results)
            else None
        )

        self._rebuild()
        for expanded_path in sorted(expanded_paths, key=lambda p: len(_paths.tokenize(p))):
            item = self._locate_path(expanded_path)
            if item is not None:
                self.tree.Expand(item)

        if selected_path:
            item = self._locate_path(selected_path)
            if item is not None:
                self._suppress_selection = True
                try:
                    self.tree.Select(item)
                finally:
                    self._suppress_selection = False

        self._refresh_search_results(current_match)
        wx.CallAfter(self._restore_scroll_position, scroll_pos)

    def _expanded_paths(self) -> List[str]:
        paths: List[str] = []

        def visit(parent) -> None:
            child = self.tree.GetFirstChild(parent)
            while child.IsOk():
                path = self.tree.GetItemData(child)
                if path is not None and self.tree.IsExpanded(child):
                    paths.append(path)
                    visit(child)
                child = self.tree.GetNextSibling(child)

        visit(self.tree.GetRootItem())
        return paths

    def _restore_scroll_position(self, position: int) -> None:
        try:
            self.tree.SetScrollPos(wx.VERTICAL, position)
            self.tree.Refresh()
        except RuntimeError:
            # A queued CallAfter may outlive the window during shutdown.
            pass

    def _append_children(self, parent_item, path: str) -> None:
        assert self._session is not None
        for summary in api.list_nodes(self._session, path or None):
            label = self._short_label(summary.path)
            if summary.display_name:
                label = f'{self._named_item_label(summary.path)} "{summary.display_name}"'
            item = self.tree.AppendItem(parent_item, label)
            self.tree.SetItemText(item, 1, summary.record_type)
            self.tree.SetItemText(item, 2, summary.evidence)
            if summary.reference_count:
                self.tree.SetItemText(item, 3, str(summary.reference_count))
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

    @staticmethod
    def _named_item_label(path: str) -> str:
        """Use a compact index for named vector items.

        The parent collection already supplies the semantic type, while the
        full path remains visible in the status bar. This keeps long effect
        names from being preceded by a redundant ``effect_descriptions``
        prefix and works equally well for other named vector entries.
        """

        tail = path.rsplit(".", 1)[-1]
        if tail.endswith("]") and "[" in tail:
            return tail[tail.rfind("[") :]
        return tail

    def _kind_of(self, path: str) -> str:
        from ..editor import nodes as _nodes

        return _nodes.classify(_paths.get_path(self._session.working, path))

    def _has_children(self, path: str) -> bool:
        assert self._session is not None
        from ..editor import nodes as _nodes

        return len(_nodes.child_paths(self._session.working, path)) > 0

    def _expand_item(self, item, path: str) -> None:
        first_child = self.tree.GetFirstChild(item)
        if first_child.IsOk() and self.tree.GetItemData(first_child) is None:
            self.tree.DeleteItem(first_child)
            self._append_children(item, path)

    def _on_expanding(self, event: dv.TreeListEvent) -> None:
        item = event.GetItem()
        path = self.tree.GetItemData(item)
        if path is None:
            return
        self._expand_item(item, path)

    def _on_selection_changed(self, event: dv.TreeListEvent) -> None:
        if self._suppress_selection:
            return
        item = event.GetItem()
        path = self.tree.GetItemData(item)
        if path is not None:
            self._on_select(path)

    # --- reveal a path found elsewhere (search, or a cross-reference jump) --

    def reveal(self, path: str) -> None:
        if self._session is None:
            return
        item = self._locate_path(path)
        if item is None:
            return
        self.tree.EnsureVisible(item)
        self._suppress_selection = True
        try:
            self.tree.Select(item)
        finally:
            self._suppress_selection = False
        self._on_select(path)

    def _locate_path(self, path: str):
        tokens = _paths.tokenize(path)
        item = self.tree.GetRootItem()
        for i in range(len(tokens)):
            prefix = _paths.format_tokens(tokens[: i + 1])
            child = self._find_child(item, prefix)
            if child is None:
                self._expand_item(item, self.tree.GetItemData(item) or "")
                child = self._find_child(item, prefix)
            if child is None:
                return None  # e.g. an index that no longer exists after an edit
            item = child
            if i < len(tokens) - 1:
                self.tree.Expand(item)
        return item

    def _find_child(self, parent_item, path: str):
        child = self.tree.GetFirstChild(parent_item)
        while child.IsOk():
            if self.tree.GetItemData(child) == path:
                return child
            child = self.tree.GetNextSibling(child)
        return None

    # --- search -------------------------------------------------------------

    def _reset_search(self) -> None:
        self._search_results = []
        self._search_cursor = -1
        self.search_status.SetLabel("")

    def _on_search_cancel(self, _event: wx.CommandEvent) -> None:
        self.search.SetValue("")
        self._reset_search()

    def _on_search_text(self, _event: wx.CommandEvent) -> None:
        if self._search_timer is not None:
            self._search_timer.Stop()
        self._search_timer = wx.CallLater(_SEARCH_DEBOUNCE_MS, self._run_search)

    def _run_search(self) -> None:
        if self._session is None:
            return
        query = self.search.GetValue()
        if not query.strip():
            self._reset_search()
            return
        ref_index = build_reference_index(self._session.working)
        summaries = find_nodes(self._session.working, ref_index, query)
        self._search_results = [s.path for s in summaries]
        self._search_cursor = -1
        if not self._search_results:
            self.search_status.SetLabel("no matches")
            return
        self._on_search_next(None)

    def _refresh_search_results(self, current_match: Optional[str]) -> None:
        """Recompute a live search without navigating away during refresh."""

        if self._session is None:
            return
        query = self.search.GetValue()
        if not query.strip():
            self._reset_search()
            return
        ref_index = build_reference_index(self._session.working)
        summaries = find_nodes(self._session.working, ref_index, query)
        self._search_results = [summary.path for summary in summaries]
        if not self._search_results:
            self._search_cursor = -1
            self.search_status.SetLabel("no matches")
            return
        if current_match in self._search_results:
            self._search_cursor = self._search_results.index(current_match)
        else:
            self._search_cursor = min(max(self._search_cursor, 0), len(self._search_results) - 1)
        path = self._search_results[self._search_cursor]
        self.search_status.SetLabel(f"{self._search_cursor + 1} of {len(self._search_results)}: {path}")

    def _on_search_next(self, _event: Optional[wx.CommandEvent]) -> None:
        if not self._search_results:
            self._run_search()
            return
        self._search_cursor = (self._search_cursor + 1) % len(self._search_results)
        path = self._search_results[self._search_cursor]
        self.search_status.SetLabel(f"{self._search_cursor + 1} of {len(self._search_results)}: {path}")
        self.reveal(path)
