"""Diagnostics/references pane: parser-reported errors/warnings plus the
live change log, per effdir-editor-spec.md's "Workspace layout". Rows are
colour-coded by severity (error/warning/info) or "change", matching how
IDE problem panels distinguish row kinds at a glance.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

import wx
import wx.dataview as dv

from ..editor.session import Change
from ..wire import Diagnostic

_ROW_COLOURS = {
    "error": wx.Colour(200, 60, 60),
    "warning": wx.Colour(170, 130, 20),
    "info": wx.Colour(90, 90, 90),
    "change": wx.Colour(60, 110, 190),
}

_COLUMNS = ("Severity", "Code", "Path", "Message")


class _DiagnosticsModel(dv.DataViewIndexListModel):
    def __init__(self) -> None:
        super().__init__(0)
        self._rows: List[Tuple[str, str, str, str]] = []

    def set_rows(self, rows: List[Tuple[str, str, str, str]]) -> None:
        old_count = len(self._rows)
        self._rows = rows
        self.Reset(len(rows))
        if old_count != len(rows):
            pass  # Reset() already notifies the control of the new row count

    def row_severity(self, row: int) -> str:
        return self._rows[row][0]

    # --- dv.DataViewIndexListModel overrides ---

    def GetColumnCount(self) -> int:
        return len(_COLUMNS)

    def GetColumnType(self, col: int) -> str:
        return "string"

    def GetValueByRow(self, row: int, col: int):
        return self._rows[row][col]

    def SetValueByRow(self, value, row: int, col: int) -> bool:
        return False  # read-only

    def GetAttrByRow(self, row: int, col: int, attr: dv.DataViewItemAttr) -> bool:
        colour = _ROW_COLOURS.get(self._rows[row][0])
        if colour is None:
            return False
        attr.SetColour(colour)
        return True


class DiagnosticsPanel(wx.Panel):
    def __init__(self, parent, on_activate_path: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self._on_activate_path = on_activate_path

        self._model = _DiagnosticsModel()
        self.list = dv.DataViewCtrl(self, style=dv.DV_ROW_LINES)
        self.list.AssociateModel(self._model)
        self.list.AppendTextColumn(_COLUMNS[0], 0, width=70)
        self.list.AppendTextColumn(_COLUMNS[1], 1, width=140)
        self.list.AppendTextColumn(_COLUMNS[2], 2, width=160)
        self.list.AppendTextColumn(_COLUMNS[3], 3, width=420)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.list, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.list.Bind(dv.EVT_DATAVIEW_ITEM_ACTIVATED, self._on_item_activated)

    def show(self, diagnostics: List[Diagnostic], changes: List[Change]) -> None:
        rows: List[Tuple[str, str, str, str]] = []
        for d in diagnostics:
            rows.append((d.severity, d.code, d.path or "", d.message))
        for c in changes:
            rows.append(("change", c.reason, c.path, f"{c.before!r} -> {c.after!r}"))
        self._model.set_rows(rows)

    def _on_item_activated(self, event: dv.DataViewEvent) -> None:
        row = self._model.GetRow(event.GetItem())
        path = self._model.GetValueByRow(row, 2)
        if path and self._on_activate_path:
            self._on_activate_path(path)
