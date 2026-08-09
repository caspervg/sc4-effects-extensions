"""Small, dependency-free line view for scalar curve vectors."""

from __future__ import annotations

import math
from typing import Callable, Optional, Sequence

import wx


class _CurveCanvas(wx.Panel):
    def __init__(self, parent, on_select: Callable[[int], None], on_commit: Callable[[int, float], None]):
        super().__init__(parent)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self._values: list[float] = []
        self._selected = -1
        self._dragging = False
        self._drag_changed = False
        self._on_select = on_select
        self._on_commit = on_commit
        self.SetMinSize(self.FromDIP((260, 150)))
        self.SetToolTip("Click a sample. Drag it to change its value.")
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)

    def set_values(self, values: Sequence[float], selected: int = -1) -> None:
        self._values = [float(value) for value in values]
        self._selected = selected if 0 <= selected < len(self._values) else -1
        self.Refresh()

    def _plot_rect(self) -> tuple[int, int, int, int]:
        width, height = self.GetClientSize()
        left = self.FromDIP(42)
        top = self.FromDIP(12)
        right = max(left + 1, width - self.FromDIP(12))
        bottom = max(top + 1, height - self.FromDIP(26))
        return left, top, right, bottom

    def _bounds(self) -> tuple[float, float]:
        if not self._values:
            return 0.0, 1.0
        low = min(self._values)
        high = max(self._values)
        if low == high:
            padding = max(1.0, abs(low) * 0.1)
            return low - padding, high + padding
        padding = (high - low) * 0.08
        return low - padding, high + padding

    def _point(self, index: int, low: float, high: float) -> tuple[int, int]:
        left, top, right, bottom = self._plot_rect()
        x = left if len(self._values) <= 1 else left + round((right - left) * index / (len(self._values) - 1))
        y = bottom - round((self._values[index] - low) / (high - low) * (bottom - top))
        return x, y

    def _value_from_y(self, y: int, low: float, high: float) -> float:
        _, top, _, bottom = self._plot_rect()
        y = max(top, min(bottom, y))
        return high - (y - top) / max(1, bottom - top) * (high - low)

    def _nearest_index(self, position: wx.Point) -> int:
        if not self._values:
            return -1
        low, high = self._bounds()
        points = [self._point(index, low, high) for index in range(len(self._values))]
        return min(range(len(points)), key=lambda index: (points[index][0] - position.x) ** 2 + (points[index][1] - position.y) ** 2)

    def _on_left_down(self, event: wx.MouseEvent) -> None:
        index = self._nearest_index(event.GetPosition())
        if index < 0:
            return
        self._selected = index
        self._dragging = True
        self._drag_changed = False
        self.CaptureMouse()
        self._on_select(index)

    def _on_motion(self, event: wx.MouseEvent) -> None:
        if self._dragging and event.Dragging() and event.LeftIsDown():
            self._update_drag(event.GetY())

    def _update_drag(self, y: int) -> None:
        if self._selected < 0:
            return
        low, high = self._bounds()
        self._values[self._selected] = self._value_from_y(y, low, high)
        self._drag_changed = True
        self.Refresh()
        self._on_select(self._selected)

    def _on_left_up(self, _event: wx.MouseEvent) -> None:
        if not self._dragging:
            return
        self._dragging = False
        if self.HasCapture():
            self.ReleaseMouse()
        if self._drag_changed and self._selected >= 0:
            self._on_commit(self._selected, self._values[self._selected])

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        background = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
        dc.SetBackground(wx.Brush(background))
        dc.Clear()
        left, top, right, bottom = self._plot_rect()
        if not self._values:
            dc.SetTextForeground(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
            dc.DrawText("No samples", left, top + (bottom - top) // 2)
            return

        low, high = self._bounds()
        grid_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)
        dc.SetPen(wx.Pen(grid_colour, 1))
        dc.SetTextForeground(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
        for fraction in (0.0, 0.5, 1.0):
            y = bottom - round((bottom - top) * fraction)
            dc.DrawLine(left, y, right, y)
        dc.DrawText(f"{high:g}", 4, top - self.FromDIP(5))
        dc.DrawText(f"{low:g}", 4, bottom - self.FromDIP(8))
        dc.DrawText("sample", left, bottom + self.FromDIP(6))

        line_colour = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        dc.SetPen(wx.Pen(line_colour, self.FromDIP(2)))
        points = [self._point(index, low, high) for index in range(len(self._values))]
        if len(points) > 1:
            dc.DrawLines(points)
        dc.SetBrush(wx.Brush(line_colour))
        dc.SetPen(wx.Pen(background, 1))
        radius = self.FromDIP(4)
        for index, (x, y) in enumerate(points):
            dc.DrawCircle(x, y, radius if index == self._selected else max(2, radius - 1))


class CurveEditorDialog(wx.Dialog):
    """Modal editor for one fixed-size scalar curve vector."""

    def __init__(
        self,
        parent,
        title: str,
        path: str,
        commands: Sequence[str],
        values: Sequence[float],
        selected: int = -1,
    ):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._values = [float(value) for value in values]
        self._selected = selected if 0 <= selected < len(self._values) else (0 if self._values else -1)

        heading = wx.StaticText(self, label="Curve editor")
        heading_font = heading.GetFont()
        heading_font.SetWeight(wx.FONTWEIGHT_BOLD)
        heading.SetFont(heading_font)
        command_text = ", ".join(commands) if commands else "scalar curve"
        meta = wx.StaticText(
            self,
            label=f"{path}   ·   {command_text}   ·   {len(self._values)} samples",
        )
        meta.SetFont(meta.GetFont().Smaller())

        self.canvas = _CurveCanvas(self, self._on_canvas_select, self._commit_drag)
        self.canvas.SetMinSize(self.FromDIP((500, 320)))

        self.samples = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES)
        self.samples.InsertColumn(0, "Sample", width=self.FromDIP(90))
        self.samples.InsertColumn(1, "Value", width=self.FromDIP(130))
        self.samples.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_sample_selected)
        self.samples.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_sample_activated)

        self.sample_label = wx.StaticText(self, label="Sample —")
        self.value = wx.TextCtrl(self, value="", style=wx.TE_PROCESS_ENTER)
        self.value.SetMinSize(self.FromDIP((120, -1)))
        self.apply = wx.Button(self, label="Apply value")
        self.add = wx.Button(self, label="Add sample")
        self.delete = wx.Button(self, label="Delete sample")
        self.apply.Bind(wx.EVT_BUTTON, self._on_apply)
        self.add.Bind(wx.EVT_BUTTON, self._on_add)
        self.delete.Bind(wx.EVT_BUTTON, self._on_delete)
        self.value.Bind(wx.EVT_TEXT_ENTER, self._on_apply)

        side = wx.BoxSizer(wx.VERTICAL)
        side.Add(wx.StaticText(self, label="Samples"), 0, wx.EXPAND | wx.BOTTOM, self.FromDIP(4))
        side.Add(self.samples, 1, wx.EXPAND)
        controls = wx.BoxSizer(wx.HORIZONTAL)
        controls.Add(self.sample_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.FromDIP(8))
        controls.Add(self.value, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.FromDIP(6))
        controls.Add(self.apply, 0, wx.ALIGN_CENTER_VERTICAL)
        side.Add(controls, 0, wx.EXPAND | wx.TOP, self.FromDIP(6))
        sample_buttons = wx.BoxSizer(wx.HORIZONTAL)
        sample_buttons.Add(self.add, 0, wx.RIGHT, self.FromDIP(6))
        sample_buttons.Add(self.delete, 0)
        side.Add(sample_buttons, 0, wx.ALIGN_RIGHT | wx.TOP, self.FromDIP(6))
        side.SetMinSize(self.FromDIP((250, -1)))

        body = wx.BoxSizer(wx.HORIZONTAL)
        body.Add(self.canvas, 1, wx.EXPAND | wx.RIGHT, self.FromDIP(8))
        body.Add(side, 0, wx.EXPAND)

        note = wx.StaticText(self, label="The horizontal axis is the sample index. Add or delete samples to change the curve length.")
        note.SetFont(note.GetFont().Smaller())
        buttons = wx.StdDialogButtonSizer()
        ok = wx.Button(self, wx.ID_OK, "OK")
        cancel = wx.Button(self, wx.ID_CANCEL, "Cancel")
        ok.SetDefault()
        ok.Bind(wx.EVT_BUTTON, self._on_ok)
        buttons.AddButton(ok)
        buttons.AddButton(cancel)
        buttons.Realize()

        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(heading, 0, wx.EXPAND)
        layout.Add(meta, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, self.FromDIP(4))
        layout.Add(body, 1, wx.EXPAND)
        layout.Add(note, 0, wx.EXPAND | wx.TOP, self.FromDIP(6))
        layout.Add(buttons, 0, wx.ALIGN_RIGHT | wx.TOP, self.FromDIP(8))
        self.SetSizer(layout)
        self.SetMinSize(self.FromDIP((820, 480)))
        self._load_samples()
        self._show_selected()
        self.Layout()

    def values(self) -> list[float]:
        return list(self._values)

    def _load_samples(self) -> None:
        self.samples.DeleteAllItems()
        for index, value in enumerate(self._values):
            row = self.samples.InsertItem(self.samples.GetItemCount(), str(index))
            self.samples.SetItem(row, 1, f"{value:g}")
        self._select_sample(self._selected)

    def _select_sample(self, index: int) -> None:
        if not 0 <= index < len(self._values):
            self._selected = -1
            self._show_selected()
            return
        self._selected = index
        self.canvas.set_values(self._values, self._selected)
        self.samples.SetItemState(index, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
        self._show_selected()

    def _on_canvas_select(self, index: int) -> None:
        self._selected = index
        self._show_selected()

    def _show_selected(self) -> None:
        if self._selected < 0 or self._selected >= len(self._values):
            self.sample_label.SetLabel("Sample —")
            self.value.ChangeValue("")
            return
        self.sample_label.SetLabel(f"Sample {self._selected}")
        self.value.ChangeValue(f"{self._values[self._selected]:g}")

    def _on_sample_selected(self, event: wx.ListEvent) -> None:
        self._select_sample(event.GetIndex())

    def _on_sample_activated(self, _event: wx.ListEvent) -> None:
        self.value.SetFocus()
        self.value.SelectAll()

    def _commit_drag(self, index: int, value: float) -> None:
        self._selected = index
        self._values[index] = value
        self.samples.SetItem(index, 1, f"{value:g}")
        self._show_selected()

    def _read_value(self) -> Optional[float]:
        try:
            value = float(self.value.GetValue())
        except ValueError:
            value = None
        if value is None or not math.isfinite(value):
            wx.MessageBox("Enter a finite number.", "Invalid curve value", wx.OK | wx.ICON_WARNING, self)
            self.value.SetFocus()
            self.value.SelectAll()
            return None
        return value

    def _on_apply(self, _event: wx.CommandEvent) -> None:
        if self._selected < 0:
            return
        value = self._read_value()
        if value is None:
            return
        self._values[self._selected] = value
        self.samples.SetItem(self._selected, 1, f"{value:g}")
        self.canvas.set_values(self._values, self._selected)
        self._show_selected()

    def _on_add(self, _event: wx.CommandEvent) -> None:
        insert_at = self._selected + 1 if self._selected >= 0 else len(self._values)
        value = self._values[self._selected] if self._selected >= 0 else 0.0
        self._values.insert(insert_at, value)
        self._selected = insert_at
        self._load_samples()

    def _on_delete(self, _event: wx.CommandEvent) -> None:
        if self._selected < 0:
            return
        del self._values[self._selected]
        self._selected = min(self._selected, len(self._values) - 1)
        self._load_samples()

    def _on_ok(self, _event: wx.CommandEvent) -> None:
        if self._selected >= 0 and self._read_value() is None:
            return
        if self._selected >= 0:
            value = float(self.value.GetValue())
            self._values[self._selected] = value
        self.EndModal(wx.ID_OK)


def edit_curve_dialog(
    parent,
    title: str,
    path: str,
    commands: Sequence[str],
    values: Sequence[float],
    selected: int = -1,
) -> Optional[list[float]]:
    dialog = CurveEditorDialog(parent, title, path, commands, values, selected=selected)
    try:
        if dialog.ShowModal() == wx.ID_OK:
            return dialog.values()
    finally:
        dialog.Destroy()
    return None
