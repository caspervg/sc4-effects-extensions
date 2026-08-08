"""Diagnostics/references pane: parser-reported errors/warnings plus the
live change log, per effdir-editor-spec.md's "Workspace layout".
"""

from __future__ import annotations

from typing import Callable, List, Optional

import wx
import wx.dataview as dv

from ..editor.session import Change
from ..wire import Diagnostic

_SEVERITY_COLOURS = {
    "error": wx.Colour(200, 60, 60),
    "warning": wx.Colour(170, 130, 20),
    "info": wx.Colour(90, 90, 90),
}


class DiagnosticsPanel(wx.Panel):
    def __init__(self, parent, on_activate_path: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self._on_activate_path = on_activate_path

        self.list = dv.DataViewListCtrl(self, style=dv.DV_ROW_LINES)
        self.list.AppendTextColumn("Severity", width=70)
        self.list.AppendTextColumn("Code", width=140)
        self.list.AppendTextColumn("Path", width=160)
        self.list.AppendTextColumn("Message", width=420)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.list, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.list.Bind(dv.EVT_DATAVIEW_ITEM_ACTIVATED, self._on_item_activated)

    def show(self, diagnostics: List[Diagnostic], changes: List[Change]) -> None:
        self.list.DeleteAllItems()
        for d in diagnostics:
            self.list.AppendItem([d.severity, d.code, d.path or "", d.message])
        for c in changes:
            self.list.AppendItem(["change", c.reason, c.path, f"{c.before!r} -> {c.after!r}"])

    def _on_item_activated(self, event: dv.DataViewEvent) -> None:
        row = self.list.ItemToRow(event.GetItem())
        path = self.list.GetTextValue(row, 2)
        if path and self._on_activate_path:
            self._on_activate_path(path)
