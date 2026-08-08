"""Custom-painted hex dump with a highlighted byte span (the selected
field's source_span), per effdir-editor-spec.md's "Hex + wire cursor"
pane. A plain text dump can't highlight a range cleanly, so this paints
directly rather than relying on rich-text markup.
"""

from __future__ import annotations

from typing import Optional

import wx

BYTES_PER_ROW = 16
ROW_HEIGHT = 18
ADDR_COLUMN_CHARS = 10


class HexView(wx.ScrolledWindow):
    def __init__(self, parent):
        super().__init__(parent, style=wx.BORDER_SUNKEN)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self._data: bytes = b""
        self._highlight: Optional[tuple[int, int]] = None
        self._font = wx.Font(wx.FontInfo(10).Family(wx.FONTFAMILY_TELETYPE))
        dc = wx.ClientDC(self)
        dc.SetFont(self._font)
        self._char_w, self._char_h = dc.GetTextExtent("0")
        self.SetScrollRate(0, ROW_HEIGHT)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, lambda evt: (self._update_virtual_size(), evt.Skip()))

    def set_data(self, data: bytes) -> None:
        self._data = data
        self._update_virtual_size()
        self.Refresh()

    def set_highlight(self, span: Optional[tuple[int, int]]) -> None:
        self._highlight = span
        if span is not None:
            row = span[0] // BYTES_PER_ROW
            self.Scroll(-1, row)
        self.Refresh()

    def _update_virtual_size(self) -> None:
        rows = max(1, (len(self._data) + BYTES_PER_ROW - 1) // BYTES_PER_ROW)
        width = (ADDR_COLUMN_CHARS + 2 + BYTES_PER_ROW * 3 + 2 + BYTES_PER_ROW) * self._char_w
        self.SetVirtualSize((int(width), rows * ROW_HEIGHT))

    def _on_paint(self, _evt: wx.PaintEvent) -> None:
        dc = wx.BufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        self.DoPrepareDC(dc)
        dc.SetFont(self._font)

        is_dark = wx.SystemSettings.GetAppearance().IsDark()
        addr_colour = wx.Colour(140, 140, 150) if not is_dark else wx.Colour(130, 130, 140)
        text_colour = self.GetForegroundColour()
        highlight_bg = wx.Colour(255, 213, 79) if not is_dark else wx.Colour(120, 96, 15)

        update_rect = self.GetUpdateRegion().GetBox()
        x0, y0 = self.CalcUnscrolledPosition(update_rect.GetLeft(), update_rect.GetTop())
        x1, y1 = self.CalcUnscrolledPosition(update_rect.GetRight(), update_rect.GetBottom())
        first_row = max(0, y0 // ROW_HEIGHT)
        last_row = min(len(self._data) // BYTES_PER_ROW, y1 // ROW_HEIGHT + 1)

        hex_x = (ADDR_COLUMN_CHARS + 2) * self._char_w
        ascii_x = hex_x + (BYTES_PER_ROW * 3 + 2) * self._char_w

        for row in range(first_row, last_row + 1):
            offset = row * BYTES_PER_ROW
            chunk = self._data[offset : offset + BYTES_PER_ROW]
            if not chunk:
                continue
            y = row * ROW_HEIGHT

            dc.SetTextForeground(addr_colour)
            dc.DrawText(f"{offset:08X}", 0, y)

            for i, byte in enumerate(chunk):
                pos = offset + i
                cell_x = hex_x + i * 3 * self._char_w
                if self._highlight and self._highlight[0] <= pos < self._highlight[1]:
                    dc.SetBrush(wx.Brush(highlight_bg))
                    dc.SetPen(wx.TRANSPARENT_PEN)
                    dc.DrawRectangle(cell_x, y, 2 * self._char_w + 2, ROW_HEIGHT)
                    dc.SetTextForeground(wx.BLACK)
                else:
                    dc.SetTextForeground(text_colour)
                dc.DrawText(f"{byte:02X}", cell_x, y)

            ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            for i, ch in enumerate(ascii_str):
                pos = offset + i
                cell_x = ascii_x + i * self._char_w
                if self._highlight and self._highlight[0] <= pos < self._highlight[1]:
                    dc.SetBrush(wx.Brush(highlight_bg))
                    dc.SetPen(wx.TRANSPARENT_PEN)
                    dc.DrawRectangle(cell_x, y, self._char_w, ROW_HEIGHT)
                    dc.SetTextForeground(wx.BLACK)
                else:
                    dc.SetTextForeground(text_colour)
                dc.DrawText(ch, cell_x, y)
