"""Syntax-highlighted preview of decompiled `.fx` source.

Uses `wx.stc` (Scintilla), which ships with wxPython -- no new
dependency. Scintilla has no built-in SC4-effects lexer, so this uses
the container style `STC_LEX_CONTAINER` and styles the text itself from
the token stream in `fx/highlight.py` (kept there, wx-free, so the
vocabulary lives beside the emitter that produces it and stays
unit-testable).
"""

from __future__ import annotations

import wx
import wx.stc as stc

from ..fx import highlight
from ..fx.coverage import Coverage

STYLE_DEFAULT = 0
STYLE_COMMENT = 1
STYLE_BLOCK = 2
STYLE_COMMAND = 3
STYLE_SWITCH = 4
STYLE_NUMBER = 5
STYLE_STRING = 6

_STYLE_BY_KIND = {
    highlight.COMMENT: STYLE_COMMENT,
    highlight.STRING: STYLE_STRING,
    highlight.SWITCH: STYLE_SWITCH,
    highlight.NUMBER: STYLE_NUMBER,
    highlight.BLOCK: STYLE_BLOCK,
    highlight.COMMAND: STYLE_COMMAND,
}


class FxPreview(stc.StyledTextCtrl):
    """Read-only, syntax-highlighted view of emitted fx text."""

    def __init__(self, parent: wx.Window):
        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetReadOnly(True)
        self.SetLexer(stc.STC_LEX_CONTAINER)
        self.SetMarginType(0, stc.STC_MARGIN_NUMBER)
        self.SetMarginWidth(0, self.FromDIP(44))
        self.SetUseHorizontalScrollBar(True)
        self.SetWrapMode(stc.STC_WRAP_NONE)
        self.SetTabWidth(4)
        self.SetUseTabs(False)
        self._apply_theme()
        self.Bind(stc.EVT_STC_STYLENEEDED, self._on_style_needed)

    def _apply_theme(self) -> None:
        # Follow the system theme rather than hard-coding light colours:
        # the rest of the editor is native-themed, and a light-only code
        # view is unreadable under a dark system theme.
        sys_bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
        sys_fg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        dark = sys_bg.GetLuminance() < 0.5 if hasattr(sys_bg, "GetLuminance") else False

        font = wx.Font(wx.FontInfo(10).Family(wx.FONTFAMILY_TELETYPE))
        self.StyleSetFont(stc.STC_STYLE_DEFAULT, font)
        self.StyleSetBackground(stc.STC_STYLE_DEFAULT, sys_bg)
        self.StyleSetForeground(stc.STC_STYLE_DEFAULT, sys_fg)
        self.StyleClearAll()

        palette = {
            STYLE_COMMENT: "#7f9f6f" if dark else "#3f7f3f",
            STYLE_BLOCK: "#c586c0" if dark else "#7f0055",
            STYLE_COMMAND: "#569cd6" if dark else "#00479c",
            STYLE_SWITCH: "#d7a35c" if dark else "#8a5a00",
            STYLE_NUMBER: "#b5cea8" if dark else "#1c6b30",
            STYLE_STRING: "#ce9178" if dark else "#a31515",
        }
        for style, colour in palette.items():
            self.StyleSetForeground(style, wx.Colour(colour))
            self.StyleSetBackground(style, sys_bg)
        self.StyleSetBold(STYLE_BLOCK, True)

    def set_text(self, text: str) -> None:
        self.SetReadOnly(False)
        self.SetValue(text)
        self.SetReadOnly(True)
        self.Colourise(0, -1)

    def _on_style_needed(self, evt: stc.StyledTextEvent) -> None:
        end = evt.GetPosition()
        start = self.GetEndStyled()
        line = self.LineFromPosition(start)
        start = self.PositionFromLine(line)
        self._style_range(start, end)

    def _style_range(self, start: int, end: int) -> None:
        text = self.GetTextRange(start, end)
        if not text:
            return
        # Scintilla positions are byte offsets; style spans are computed on
        # the UTF-8 encoding so non-ASCII names (the wire format does not
        # guarantee ASCII) cannot shift every later style by a byte.
        self.StartStyling(start)
        self.SetStyling(len(text.encode("utf-8")), STYLE_DEFAULT)

        for token in highlight.tokenize(text):
            byte_start = start + len(text[: token.start].encode("utf-8"))
            self.StartStyling(byte_start)
            self.SetStyling(len(token.text.encode("utf-8")), _STYLE_BY_KIND[token.kind])


class FxPreviewDialog(wx.Dialog):
    """Preview emitted fx with its coverage report, then optionally save."""

    def __init__(self, parent: wx.Window, title: str, text: str, coverage: Coverage):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetInitialSize(parent.FromDIP((900, 680)))
        self._text = text

        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH)
        self.preview = FxPreview(splitter)
        self.preview.set_text(text)

        notes_panel = wx.Panel(splitter)
        notes_sizer = wx.BoxSizer(wx.VERTICAL)
        summary = wx.StaticText(notes_panel, label=" · ".join(coverage.summary_lines()))
        summary_font = summary.GetFont()
        summary_font.MakeBold()
        summary.SetFont(summary_font)
        notes_sizer.Add(summary, 0, wx.ALL, self.FromDIP(6))

        self.notes = wx.ListCtrl(notes_panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.notes.InsertColumn(0, "Severity", width=self.FromDIP(90))
        self.notes.InsertColumn(1, "Path", width=self.FromDIP(240))
        self.notes.InsertColumn(2, "Detail", width=self.FromDIP(520))
        # Most-actionable first: an unsupported field is a real gap, an
        # ambiguous one is a judgement call, info is just bookkeeping.
        order = {"unsupported": 0, "ambiguous": 1, "info": 2}
        for note in sorted(coverage.notes, key=lambda n: (order.get(n.severity, 3), n.path)):
            row = self.notes.InsertItem(self.notes.GetItemCount(), note.severity)
            self.notes.SetItem(row, 1, note.path)
            self.notes.SetItem(row, 2, note.message)
        notes_sizer.Add(self.notes, 1, wx.EXPAND | wx.ALL, self.FromDIP(6))
        notes_panel.SetSizer(notes_sizer)

        splitter.SplitHorizontally(self.preview, notes_panel)
        splitter.SetSashGravity(0.9)
        splitter.SetMinimumPaneSize(self.FromDIP(120))

        buttons = wx.StdDialogButtonSizer()
        save = wx.Button(self, wx.ID_SAVE, "Save .fx...")
        save.SetDefault()
        buttons.AddButton(save)
        buttons.AddButton(wx.Button(self, wx.ID_CANCEL, "Close"))
        buttons.Realize()
        # Only wx.ID_OK/wx.ID_CANCEL dismiss a modal dialog on their own;
        # wx.ID_SAVE needs an explicit EndModal or the button does nothing.
        save.Bind(wx.EVT_BUTTON, lambda _evt: self.EndModal(wx.ID_SAVE))

        copy = wx.Button(self, wx.ID_COPY, "Copy to Clipboard")
        copy.Bind(wx.EVT_BUTTON, self._on_copy)

        bottom = wx.BoxSizer(wx.HORIZONTAL)
        bottom.Add(copy, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.FromDIP(8))
        bottom.AddStretchSpacer()
        bottom.Add(buttons, 0)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(splitter, 1, wx.EXPAND | wx.ALL, self.FromDIP(6))
        sizer.Add(bottom, 0, wx.EXPAND | wx.ALL, self.FromDIP(8))
        self.SetSizer(sizer)

    def _on_copy(self, _evt) -> None:
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self._text))
            wx.TheClipboard.Close()
