from __future__ import annotations

import wx

from .main_frame import MainFrame


class EffDirEditorApp(wx.App):
    def OnInit(self) -> bool:
        frame = MainFrame()
        frame.Show()
        return True


def main() -> None:
    app = EffDirEditorApp()
    app.MainLoop()
