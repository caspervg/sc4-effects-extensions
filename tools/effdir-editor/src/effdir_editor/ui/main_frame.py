"""Main window: AUI-docked 4-pane workspace wired to the headless editor
API. This module is the only place that knows about wx *and* the editor
API together -- panels below only know wx, api.py only knows the model.
"""

from __future__ import annotations

import os
from typing import Optional

import wx
import wx.aui

from ..container.adapter import DbpfEffDirSource, LocalFileEffDirSource, ResourceHandle, WriteOptions
from ..editor import api
from ..editor import nodes as _nodes
from ..editor import paths as _paths
from ..editor.session import EditorSession
from ..model.resource import default_resource, write_resource
from .diagnostics_panel import DiagnosticsPanel
from .hex_view import HexView
from .record_editor import RecordEditor
from .resource_tree import ResourceTree

COLLECTION_ITEM_TYPE_BY_ATTR = {
    "particles": "ParticleDescriptor",
    "decals": "DecalDescriptor",
    "shakes": "ShakeDescriptor",
    "lights": "LightDescriptor",
    "dynamic_particles": "DynamicParticleDescriptor",
    "brushes": "BrushDescription",
    "attractors": "AttractorDescription",
    "scrubbers": "ScrubberDescription",
    "sequences": "SequenceDescription",
    "sounds": "SoundDescription",
    "cameras": "CameraDescription",
}

ID_ADD_RECORD = wx.NewIdRef()
ID_REMOVE_RECORD = wx.NewIdRef()


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="EFFDIR Editor")
        self.SetInitialSize(self.FromDIP((1280, 860)))
        self.session: Optional[EditorSession] = None

        self._mgr = wx.aui.AuiManager(self)

        self.tree = ResourceTree(self, on_select=self._on_tree_select)
        self.record_editor = RecordEditor(self, on_change=self._on_field_changed, on_navigate=self._select_path)
        self.diagnostics = DiagnosticsPanel(self, on_activate_path=self._select_path)
        self.hex_view = HexView(self)

        self._mgr.AddPane(
            self.tree,
            wx.aui.AuiPaneInfo()
            .Left()
            .Caption("Resource")
            # AUI treats BestSize as a hint and otherwise tends to restore
            # the narrow default dock width. Keep the resource tree wide
            # enough for long effect names in the actual layout as well.
            .MinSize(self.FromDIP((560, -1)))
            .BestSize(self.FromDIP((680, -1)))
            .CloseButton(False),
        )
        self._mgr.AddPane(
            self.diagnostics,
            wx.aui.AuiPaneInfo()
            .Bottom()
            .Caption("Diagnostics")
            .MinSize(self.FromDIP((-1, 140)))
            .BestSize(self.FromDIP((-1, 200)))
            .CloseButton(False),
        )
        self._mgr.AddPane(
            self.hex_view,
            wx.aui.AuiPaneInfo()
            .Bottom()
            .Caption("Hex")
            .MinSize(self.FromDIP((-1, 160)))
            .BestSize(self.FromDIP((-1, 220)))
            .CloseButton(False),
        )
        self._mgr.AddPane(
            self.record_editor,
            wx.aui.AuiPaneInfo().CenterPane().Caption("Fields"),
        )

        self._build_menu()
        self._build_toolbar()
        self.status = self.CreateStatusBar(2)
        self.status.SetStatusWidths([-1, self.FromDIP(260)])

        self.tree.tree.Bind(wx.EVT_CONTEXT_MENU, self._on_tree_context_menu)

        self._mgr.Update()
        self._update_enabled_state()
        self.Bind(wx.EVT_CLOSE, self._on_close)

    # --- menu / toolbar ---------------------------------------------------

    def _build_menu(self) -> None:
        menu_bar = wx.MenuBar()

        file_menu = wx.Menu()
        self._append(file_menu, wx.ID_NEW, "&New Resource\tCtrl+N", self._on_new)
        self._append(file_menu, wx.ID_OPEN, "&Open...\tCtrl+O", self._on_open)
        file_menu.AppendSeparator()
        self._append(file_menu, wx.ID_SAVE, "&Save\tCtrl+S", self._on_save)
        self._append(file_menu, wx.ID_SAVEAS, "Save &As...\tCtrl+Shift+S", self._on_save_as)
        file_menu.AppendSeparator()
        self._append(file_menu, wx.ID_EXIT, "E&xit", lambda e: self.Close())
        menu_bar.Append(file_menu, "&File")

        edit_menu = wx.Menu()
        self._append(edit_menu, wx.ID_UNDO, "&Undo\tCtrl+Z", self._on_undo)
        self._append(edit_menu, wx.ID_REDO, "&Redo\tCtrl+Shift+Z", self._on_redo)
        menu_bar.Append(edit_menu, "&Edit")

        self.SetMenuBar(menu_bar)

    def _build_toolbar(self) -> None:
        tb = self.CreateToolBar()
        tb.AddTool(wx.ID_OPEN, "Open", wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN, wx.ART_TOOLBAR))
        tb.AddTool(wx.ID_SAVE, "Save", wx.ArtProvider.GetBitmap(wx.ART_FILE_SAVE, wx.ART_TOOLBAR))
        tb.AddSeparator()
        tb.AddTool(wx.ID_UNDO, "Undo", wx.ArtProvider.GetBitmap(wx.ART_UNDO, wx.ART_TOOLBAR))
        tb.AddTool(wx.ID_REDO, "Redo", wx.ArtProvider.GetBitmap(wx.ART_REDO, wx.ART_TOOLBAR))
        tb.Realize()
        self.Bind(wx.EVT_TOOL, self._on_open, id=wx.ID_OPEN)
        self.Bind(wx.EVT_TOOL, self._on_save, id=wx.ID_SAVE)
        self.Bind(wx.EVT_TOOL, self._on_undo, id=wx.ID_UNDO)
        self.Bind(wx.EVT_TOOL, self._on_redo, id=wx.ID_REDO)

    def _append(self, menu: wx.Menu, item_id, label: str, handler) -> None:
        item = menu.Append(item_id, label)
        self.Bind(wx.EVT_MENU, handler, item)

    # --- session lifecycle --------------------------------------------------

    def _load_session(self, session: EditorSession) -> None:
        self.session = session
        self.tree.load(session)
        self.record_editor.show_record(session, None)
        self._refresh_hex()
        self._refresh_diagnostics()
        self._update_enabled_state()

    def _on_new(self, _evt) -> None:
        source = LocalFileEffDirSource()
        handle = ResourceHandle(package_path="", tgi="")
        session = EditorSession(handle=handle, source=source, original_bytes=b"", working=default_resource())
        self._load_session(session)
        self.SetTitle("EFFDIR Editor — untitled")

    def _on_open(self, _evt) -> None:
        with wx.FileDialog(
            self,
            "Open EFFDIR resource",
            wildcard="SC4 package (*.dat)|*.dat|Raw EFFDIR (*.effdir;*.bin)|*.effdir;*.bin|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()

        is_dbpf = path.lower().endswith(".dat")
        tgi = ""
        if is_dbpf:
            source = DbpfEffDirSource()
            try:
                tgis = source.list_effdir_tgis(path)
            except Exception as exc:
                wx.MessageBox(f"Could not read package:\n{exc}", "Open failed", wx.OK | wx.ICON_ERROR)
                return
            if not tgis:
                wx.MessageBox("No EFFDIR resources found in this package.", "Open failed", wx.OK | wx.ICON_ERROR)
                return
            if len(tgis) == 1:
                tgi = tgis[0]
            else:
                with wx.SingleChoiceDialog(
                    self, f"{len(tgis)} EFFDIR resources found in this package:", "Choose Resource", tgis
                ) as choice_dlg:
                    if choice_dlg.ShowModal() != wx.ID_OK:
                        return
                    tgi = choice_dlg.GetStringSelection()
        else:
            source = LocalFileEffDirSource()
        handle = ResourceHandle(package_path=path, tgi=tgi)
        try:
            session = api.open(source, handle)
        except Exception as exc:  # surfaced to the user; the resource layer already fails closed
            wx.MessageBox(f"Could not open resource:\n{exc}", "Open failed", wx.OK | wx.ICON_ERROR)
            return

        self._load_session(session)
        self.SetTitle(f"EFFDIR Editor — {os.path.basename(path)}")
        if session.working.preservation.original_payload is not None:
            wx.MessageBox(
                "This resource could not be parsed (unsupported version or malformed data) "
                "and is loaded read-only; it will be written back unchanged.",
                "Unparsed resource",
                wx.OK | wx.ICON_WARNING,
            )

    def _on_save(self, _evt) -> None:
        if self.session is None:
            return
        if not self.session.handle.package_path:
            self._on_save_as(_evt)
            return
        self._commit(self.session.handle.package_path)

    def _on_save_as(self, _evt) -> None:
        if self.session is None:
            return
        with wx.FileDialog(
            self, "Save EFFDIR resource", wildcard="Raw EFFDIR (*.effdir)|*.effdir|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        if not self.session.handle.package_path:
            self.session.source = LocalFileEffDirSource()
        self.session.handle = ResourceHandle(package_path=path, tgi=self.session.handle.tgi)
        self._commit(path)

    def _commit(self, path: str) -> None:
        try:
            result = api.commit(self.session, WriteOptions(output_path=path))
        except Exception as exc:
            wx.MessageBox(f"Save failed:\n{exc}", "Save failed", wx.OK | wx.ICON_ERROR)
            return
        self.SetTitle(f"EFFDIR Editor — {os.path.basename(path)}")
        self.status.SetStatusText(f"Saved ({result.backup_path or 'no backup'})", 0)
        self._refresh_diagnostics()
        self._update_enabled_state()

    def _on_close(self, event: wx.CloseEvent) -> None:
        if self.session is not None and self.session.dirty:
            if wx.MessageBox("Discard unsaved changes?", "Unsaved changes", wx.YES_NO | wx.ICON_WARNING) != wx.YES:
                event.Veto()
                return
        self._mgr.UnInit()
        event.Skip()

    # --- undo/redo ----------------------------------------------------------

    def _on_undo(self, _evt) -> None:
        if self.session is None:
            return
        api.undo(self.session)
        self._reload_after_history_change()

    def _on_redo(self, _evt) -> None:
        if self.session is None:
            return
        api.redo(self.session)
        self._reload_after_history_change()

    def _reload_after_history_change(self) -> None:
        self.tree.refresh()
        self.record_editor.show_record(self.session, self.session.selected_path)
        self._refresh_hex()
        self._refresh_diagnostics()
        self._update_enabled_state()

    # --- tree / field interaction --------------------------------------------

    def _on_tree_select(self, path: str) -> None:
        if self.session is None:
            return
        self.session.selected_path = path
        kind = _nodes.classify(_paths.get_path(self.session.working, path))
        if kind in ("record", "value", "collection"):
            self.record_editor.show_record(self.session, path)
        else:
            self.record_editor.show_record(self.session, _paths.parent_path(path))
        self._highlight_path(path)
        self.status.SetStatusText(path, 1)

    def _select_path(self, path: str) -> None:
        self._on_tree_select(path)

    def _on_field_changed(self, path: str) -> None:
        self.tree.refresh()
        self._refresh_hex()
        self._refresh_diagnostics()
        self._update_enabled_state()
        self._highlight_path(path)

    def _highlight_path(self, path: str) -> None:
        if self.session is None:
            return
        value = _paths.get_path(self.session.working, path)
        span = getattr(value, "source_span", None)
        self.hex_view.set_highlight((span.start, span.end) if span is not None else None)

    def _refresh_hex(self) -> None:
        if self.session is None:
            self.hex_view.set_data(b"")
            return
        try:
            data = write_resource(self.session.working)
        except Exception:
            data = self.session.original_bytes
        self.hex_view.set_data(data)
        self.hex_view.set_opaque_ranges(api.opaque_ranges(self.session, len(data)))

    def _refresh_diagnostics(self) -> None:
        if self.session is None:
            self.diagnostics.show([], [])
            return
        self.diagnostics.show(api.validate(self.session), list(self.session.change_log))

    def _update_enabled_state(self) -> None:
        has_session = self.session is not None
        self.GetToolBar().EnableTool(wx.ID_SAVE, has_session)
        self.GetToolBar().EnableTool(wx.ID_UNDO, has_session and bool(self.session.undo_stack))
        self.GetToolBar().EnableTool(wx.ID_REDO, has_session and bool(self.session.redo_stack))
        dirty = has_session and self.session.dirty
        self.status.SetStatusText("Modified" if dirty else ("Ready" if has_session else "No resource open"), 0)

    # --- add/remove records ---------------------------------------------------

    def _on_tree_context_menu(self, _evt) -> None:
        if self.session is None:
            return
        item = self.tree.tree.GetSelection()
        if not item.IsOk():
            return
        path = self.tree.tree.GetItemData(item)
        if path is None:
            return
        value = _paths.get_path(self.session.working, path)
        kind = _nodes.classify(value)

        menu = wx.Menu()
        attr_name = _paths.tokenize(path)[-1] if kind == "collection" else None
        if kind == "collection" and isinstance(attr_name, str) and attr_name in COLLECTION_ITEM_TYPE_BY_ATTR:
            add_item = menu.Append(ID_ADD_RECORD, f"Add {COLLECTION_ITEM_TYPE_BY_ATTR[attr_name]}")
            self.Bind(wx.EVT_MENU, lambda e, p=path, t=COLLECTION_ITEM_TYPE_BY_ATTR[attr_name]: self._add_record(p, t), add_item)
        if path == "effect_descriptions":
            add_effect_item = menu.Append(wx.ID_ANY, "Add Effect Description...")
            self.Bind(wx.EVT_MENU, lambda e: self._add_effect(), add_effect_item)
        if kind == "record" and isinstance(_paths.tokenize(path)[-1], int):
            remove_item = menu.Append(ID_REMOVE_RECORD, "Remove")
            self.Bind(wx.EVT_MENU, lambda e, p=path: self._remove_record(p), remove_item)

        if menu.GetMenuItemCount():
            self.tree.tree.PopupMenu(menu)

    def _add_record(self, collection_path: str, record_type: str) -> None:
        api.add_record(self.session, collection_path, record_type)
        self.tree.refresh()
        self._refresh_hex()
        self._refresh_diagnostics()
        self._update_enabled_state()

    def _add_effect(self) -> None:
        dlg = wx.TextEntryDialog(self, "Effect name:", "Add Effect Description")
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetValue().strip()
            if name:
                api.add_effect(self.session, name)
                self.tree.refresh()
                self._refresh_hex()
                self._refresh_diagnostics()
                self._update_enabled_state()
        dlg.Destroy()

    def _remove_record(self, path: str) -> None:
        if wx.MessageBox(f"Remove {path}?", "Confirm removal", wx.YES_NO | wx.ICON_WARNING) != wx.YES:
            return
        api.remove_record(self.session, path)
        self.record_editor.show_record(self.session, None)
        self.tree.refresh()
        self._refresh_hex()
        self._refresh_diagnostics()
        self._update_enabled_state()
