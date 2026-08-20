"""Windows DWM thumbnail used as a zero-copy SC4 viewport."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

import wx

if os.name == "nt":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetClientRect.restype = wintypes.BOOL
    _user32.MapWindowPoints.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.POINTER(wintypes.POINT), wintypes.UINT]
    _user32.MapWindowPoints.restype = ctypes.c_int
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _dwmapi.DwmRegisterThumbnail.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.POINTER(wintypes.HANDLE)]
    _dwmapi.DwmRegisterThumbnail.restype = ctypes.c_long
    _dwmapi.DwmUnregisterThumbnail.argtypes = [wintypes.HANDLE]
    _dwmapi.DwmUnregisterThumbnail.restype = ctypes.c_long
else:
    _user32 = _dwmapi = _kernel32 = None


class _DwmThumbnailProperties(ctypes.Structure):
    _fields_ = [
        ("dwFlags", wintypes.DWORD),
        ("rcDestination", wintypes.RECT),
        ("rcSource", wintypes.RECT),
        ("opacity", ctypes.c_ubyte),
        ("fVisible", wintypes.BOOL),
        ("fSourceClientAreaOnly", wintypes.BOOL),
    ]


if _dwmapi is not None:
    _dwmapi.DwmUpdateThumbnailProperties.argtypes = [wintypes.HANDLE, ctypes.POINTER(_DwmThumbnailProperties)]
    _dwmapi.DwmUpdateThumbnailProperties.restype = ctypes.c_long

_DWM_TNP_RECTDESTINATION = 0x1
_DWM_TNP_VISIBLE = 0x8
_DWM_TNP_SOURCECLIENTAREAONLY = 0x10


def _fit_rect(
    left: int, top: int, width: int, height: int, source_width: int, source_height: int
) -> tuple[int, int, int, int]:
    if width * source_height > height * source_width:
        fitted_width = height * source_width // source_height
        left += (width - fitted_width) // 2
        width = fitted_width
    else:
        fitted_height = width * source_height // source_width
        top += (height - fitted_height) // 2
        height = fitted_height
    return left, top, left + max(width, 1), top + max(height, 1)


def find_sc4_window() -> int | None:
    if _user32 is None:
        return None
    matches: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd, _lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        process_id = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        process = _kernel32.OpenProcess(0x1000, False, process_id.value)
        path = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path))
        if process and _kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(length)):
            is_sc4 = os.path.basename(path.value).casefold() == "simcity 4.exe"
        else:
            is_sc4 = False
        if process:
            _kernel32.CloseHandle(process)
        if is_sc4:
            matches.append(int(hwnd))
        return True

    _user32.EnumWindows(visit, 0)
    return matches[0] if matches else None


class DwmPreviewPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent, style=wx.BORDER_SIMPLE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(wx.Colour(20, 22, 26))
        self.SetMinSize(self.FromDIP((420, 280)))
        self._thumbnail = wintypes.HANDLE()
        self._source_hwnd: int | None = None
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self._timer)
        self.Bind(wx.EVT_SIZE, self._on_geometry_changed)
        self.Bind(wx.EVT_MOVE, self._on_geometry_changed)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self._timer.Start(1000)
        wx.CallAfter(self.refresh)

    @property
    def connected(self) -> bool:
        return bool(self._thumbnail.value)

    def refresh(self) -> None:
        if _dwmapi is None:
            return
        source = find_sc4_window()
        if source != self._source_hwnd:
            self._detach()
            if source:
                thumbnail = wintypes.HANDLE()
                destination = int(self.GetTopLevelParent().GetHandle())
                if _dwmapi.DwmRegisterThumbnail(destination, source, ctypes.byref(thumbnail)) == 0:
                    self._thumbnail = thumbnail
                    self._source_hwnd = source
        self._update_thumbnail()
        self.Refresh(False)

    def _update_thumbnail(self) -> None:
        if not self.connected:
            return
        frame = self.GetTopLevelParent()
        origin = wintypes.POINT()
        rect = wintypes.RECT()
        source_rect = wintypes.RECT()
        _user32.MapWindowPoints(int(self.GetHandle()), int(frame.GetHandle()), ctypes.byref(origin), 1)
        _user32.GetClientRect(int(self.GetHandle()), ctypes.byref(rect))
        if not _user32.GetClientRect(self._source_hwnd, ctypes.byref(source_rect)) or not (
            source_rect.right and source_rect.bottom
        ):
            return
        properties = _DwmThumbnailProperties()
        properties.dwFlags = _DWM_TNP_RECTDESTINATION | _DWM_TNP_VISIBLE | _DWM_TNP_SOURCECLIENTAREAONLY
        properties.rcDestination = wintypes.RECT(
            *_fit_rect(origin.x, origin.y, rect.right, rect.bottom, source_rect.right, source_rect.bottom)
        )
        properties.fVisible = True
        properties.fSourceClientAreaOnly = True
        _dwmapi.DwmUpdateThumbnailProperties(self._thumbnail, ctypes.byref(properties))

    def _detach(self) -> None:
        if self.connected and _dwmapi is not None:
            _dwmapi.DwmUnregisterThumbnail(self._thumbnail)
        self._thumbnail = wintypes.HANDLE()
        self._source_hwnd = None

    def _on_timer(self, _event) -> None:
        self.refresh()

    def _on_geometry_changed(self, event) -> None:
        wx.CallAfter(self._update_thumbnail)
        event.Skip()

    def _on_destroy(self, event) -> None:
        if event.GetEventObject() is self:
            self._timer.Stop()
            self._detach()
        event.Skip()

    def _on_paint(self, _event) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        if not self.connected:
            dc.SetTextForeground(wx.Colour(180, 184, 190))
            text = "Start SimCity 4 in windowed or borderless mode"
            width, height = dc.GetTextExtent(text)
            size = self.GetClientSize()
            dc.DrawText(text, max(8, (size.width - width) // 2), max(8, (size.height - height) // 2))
