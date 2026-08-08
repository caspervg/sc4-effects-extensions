from __future__ import annotations

# This must run before wxPython is imported: wxMSW creates its native
# application state during import and cannot reliably change process DPI
# awareness afterwards.
from .dpi import enable_windows_dpi_awareness

enable_windows_dpi_awareness()

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
