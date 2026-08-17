"""Picker for choosing among multiple EFFDIR-type resources found in one
DBPF package. Shows what the DBPF index already knows about each entry --
TGI, stored size, compression -- without decompressing or parsing any
entry's EFFDIR payload; see container/adapter.py's `EffDirEntryInfo`.
"""

from __future__ import annotations

from typing import List, Optional

import wx

from ..container.adapter import EffDirEntryInfo


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB"):
        if value < 1024 or unit == "MB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} MB"


class EffDirPickerDialog(wx.Dialog):
    def __init__(self, parent: wx.Window, entries: List[EffDirEntryInfo]):
        super().__init__(parent, title="Choose EFFDIR Resource", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._entries = entries
        self.SetInitialSize(self.FromDIP((640, 320)))

        message = wx.StaticText(self, label=f"{len(entries)} EFFDIR resources were found in this package:")

        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES | wx.LC_VRULES)
        self.list.InsertColumn(0, "Type", width=self.FromDIP(100))
        self.list.InsertColumn(1, "Group", width=self.FromDIP(100))
        self.list.InsertColumn(2, "Instance", width=self.FromDIP(100))
        self.list.InsertColumn(3, "Size", width=self.FromDIP(90))
        self.list.InsertColumn(4, "Compressed", width=self.FromDIP(90))
        for entry in entries:
            row = self.list.InsertItem(self.list.GetItemCount(), f"{entry.type_id:08X}")
            self.list.SetItem(row, 1, f"{entry.group_id:08X}")
            self.list.SetItem(row, 2, f"{entry.instance_id:08X}")
            self.list.SetItem(row, 3, _format_size(entry.size))
            self.list.SetItem(row, 4, "Yes" if entry.compressed else "No")
        if entries:
            self.list.Select(0)
            self.list.Focus(0)

        buttons = wx.StdDialogButtonSizer()
        ok = wx.Button(self, wx.ID_OK, "Open")
        ok.SetDefault()
        buttons.AddButton(ok)
        buttons.AddButton(wx.Button(self, wx.ID_CANCEL, "Cancel"))
        buttons.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(message, 0, wx.EXPAND | wx.ALL, self.FromDIP(8))
        sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, self.FromDIP(8))
        sizer.Add(buttons, 0, wx.EXPAND | wx.ALL, self.FromDIP(8))
        self.SetSizer(sizer)

        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_activate)

    def _on_activate(self, _evt: wx.ListEvent) -> None:
        self.EndModal(wx.ID_OK)

    def selected_tgi(self) -> Optional[str]:
        index = self.list.GetFirstSelected()
        if index < 0:
            return None
        return self._entries[index].tgi
