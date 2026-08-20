"""Dockable live SC4 viewport and effects-preview controls."""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import wx

from ..game_client import make_command, send_command
from .dwm_preview import DwmPreviewPanel


class GamePreviewPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self._busy = False
        self._pending: tuple[str, bool] | None = None
        self._preview_directory = tempfile.TemporaryDirectory(prefix="effdir-editor-")

        self.viewport = DwmPreviewPanel(self)
        self.connection = wx.StaticText(self, label="SC4 command connection not checked")
        self.effect_name = wx.TextCtrl(self)
        self.fx_path = wx.FilePickerCtrl(self, message="Select an fx file", wildcard="fx source (*.fx)|*.fx")

        connect = wx.Button(self, label="Check")
        reload_fx = wx.Button(self, label="Load / Reload .fx")
        play = wx.Button(self, label="Preview")
        stop = wx.Button(self, label="Stop")

        connect.Bind(wx.EVT_BUTTON, lambda _event: self._run("EffectsStatus"))
        reload_fx.Bind(wx.EVT_BUTTON, self._on_reload_fx)
        play.Bind(wx.EVT_BUTTON, self._on_preview)
        stop.Bind(wx.EVT_BUTTON, lambda _event: self._run("EffectsPreviewStop"))

        top = wx.BoxSizer(wx.HORIZONTAL)
        top.Add(self.connection, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.FromDIP(6))
        top.Add(connect)

        file_row = wx.BoxSizer(wx.HORIZONTAL)
        file_row.Add(self.fx_path, 1, wx.RIGHT, self.FromDIP(6))
        file_row.Add(reload_fx)

        effect_row = wx.BoxSizer(wx.HORIZONTAL)
        effect_row.Add(wx.StaticText(self, label="Effect"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.FromDIP(6))
        effect_row.Add(self.effect_name, 1, wx.RIGHT, self.FromDIP(6))
        effect_row.Add(play, 0, wx.RIGHT, self.FromDIP(4))
        effect_row.Add(stop)

        self.transform: dict[str, wx.SpinCtrlDouble] = {}
        transform_grid = wx.FlexGridSizer(cols=4, hgap=self.FromDIP(5), vgap=self.FromDIP(4))
        for label, default, increment in (
            ("X", 512.0, 1.0), ("Y", 280.0, 1.0), ("Z", 512.0, 1.0),
            ("RX", 0.0, 1.0), ("RY", 0.0, 1.0), ("RZ", 0.0, 1.0), ("Scale", 1.0, 0.05),
        ):
            transform_grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            control = wx.SpinCtrlDouble(self, min=-100000.0, max=100000.0, initial=default, inc=increment)
            control.SetDigits(2)
            control.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_transform)
            self.transform[label] = control
            transform_grid.Add(control, 1, wx.EXPAND)
        transform_grid.AddGrowableCol(1)
        transform_grid.AddGrowableCol(3)

        camera_box = wx.StaticBoxSizer(wx.VERTICAL, self, "Camera")
        camera_parent = camera_box.GetStaticBox()
        camera_grid = wx.GridSizer(rows=3, cols=3, hgap=self.FromDIP(4), vgap=self.FromDIP(4))
        for label, command, help_text in (
            ("↶", "RotateCCW", "Rotate counterclockwise"),
            ("↑", "ScrollUpOnce", "Pan up"),
            ("↷", "RotateCW", "Rotate clockwise"),
            ("←", "ScrollLeftOnce", "Pan left"),
            ("XYZ", None, "Center camera on the effect X/Y/Z position"),
            ("→", "ScrollRightOnce", "Pan right"),
            ("−", "ZoomOut", "Zoom out"),
            ("↓", "ScrollDownOnce", "Pan down"),
            ("+", "ZoomIn", "Zoom in"),
        ):
            button = wx.Button(camera_parent, label=label)
            button.SetToolTip(help_text)
            button.SetName(help_text)
            if command is None:
                button.Bind(wx.EVT_BUTTON, self._on_camera_target)
            else:
                button.Bind(wx.EVT_BUTTON, lambda _event, value=command: self._run(value))
            camera_grid.Add(button, 1, wx.EXPAND)
        camera_box.Add(camera_grid, 1, wx.EXPAND | wx.ALL, self.FromDIP(4))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.viewport, 1, wx.EXPAND | wx.BOTTOM, self.FromDIP(8))
        sizer.Add(camera_box, 0, wx.EXPAND | wx.BOTTOM, self.FromDIP(6))
        sizer.Add(top, 0, wx.EXPAND | wx.BOTTOM, self.FromDIP(6))
        sizer.Add(file_row, 0, wx.EXPAND | wx.BOTTOM, self.FromDIP(6))
        sizer.Add(effect_row, 0, wx.EXPAND | wx.BOTTOM, self.FromDIP(6))
        sizer.Add(transform_grid, 0, wx.EXPAND)
        self.SetSizer(sizer)

    def set_effect_name(self, name: str) -> None:
        self.effect_name.ChangeValue(name)

    def load_fx_text(self, text: str) -> None:
        path = Path(self._preview_directory.name, "preview.fx")
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            self.connection.SetLabel(f"Could not write preview .fx: {exc}")
            return
        self.fx_path.SetPath(str(path))
        self._run(make_command("EffectsLoadFx", path))

    def _values(self) -> list[float]:
        return [self.transform[key].GetValue() for key in ("X", "Y", "Z", "RX", "RY", "RZ", "Scale")]

    def _on_reload_fx(self, _event) -> None:
        path = self.fx_path.GetPath()
        if path:
            self._run(make_command("EffectsLoadFx", path))

    def _on_preview(self, _event) -> None:
        name = self.effect_name.GetValue().strip()
        if name:
            self._run(make_command("EffectsPreviewStart", name, *self._values()))

    def _on_transform(self, _event) -> None:
        self._run(make_command("EffectsPreviewTransform", *self._values()), quiet=True)

    def _on_camera_target(self, _event) -> None:
        self._run(make_command("SetViewTarget", "position", *self._values()[:3]))

    def _run(self, command: str, *, quiet: bool = False) -> None:
        if self._busy:
            if not quiet or self._pending is None or self._pending[1]:
                self._pending = command, quiet
            return
        self._busy = True
        self.connection.SetLabel("Sending…")

        def work() -> None:
            try:
                response = send_command(command)
            except (OSError, ValueError) as exc:
                response = f"Command failed: {exc}"
            wx.CallAfter(self._complete, response, quiet)

        threading.Thread(target=work, daemon=True).start()

    def _complete(self, response: str, quiet: bool) -> None:
        self._busy = False
        self.connection.SetLabel(response or "Command completed")
        if not quiet:
            self.connection.GetParent().Layout()
        if pending := self._pending:
            self._pending = None
            self._run(pending[0], quiet=pending[1])
