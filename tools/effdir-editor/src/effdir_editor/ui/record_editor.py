"""Record editor: a property grid over one record's direct scalar/string/
value fields (child records/collections are navigated via the tree, not
nested here). Shows binding label + evidence as help text, and a detail
strip for path/wire-type/evidence, per effdir-editor-spec.md's "Field
presentation".
"""

from __future__ import annotations

from typing import Callable, Optional

import wx
import wx.propgrid as wxpg

from ..editor import api
from ..editor import nodes as _nodes
from ..editor import paths as _paths
from ..editor.session import EditorSession
from ..wire import Bounds2, Bounds3, Raw, Vec2, Vec3

_KEY_LABEL_SUBSTRINGS = ("key", "_id")


def _looks_like_key(label: str) -> bool:
    """SC4 resource keys, message/group/instance IDs, etc. are
    conventionally shown in hex across SC4 modding tools."""

    lowered = label.lower()
    if lowered.startswith("marker"):
        return False
    return any(s in lowered for s in _KEY_LABEL_SUBSTRINGS)


class RecordEditor(wx.Panel):
    def __init__(self, parent, on_change: Callable[[str], None]):
        super().__init__(parent)
        self._session: Optional[EditorSession] = None
        self._record_path: Optional[str] = None
        self._on_change = on_change

        self.grid = wxpg.PropertyGridManager(
            self, style=wxpg.PG_SPLITTER_AUTO_CENTER | wxpg.PGMAN_DEFAULT_STYLE
        )
        self.grid.AddPage("Fields")
        self.detail = wx.StaticText(self, label=" ")
        self.detail.SetFont(self.detail.GetFont().Smaller())

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.grid, 1, wx.EXPAND)
        sizer.Add(self.detail, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.SetSizer(sizer)

        self.grid.Bind(wxpg.EVT_PG_CHANGED, self._on_prop_changed)
        self.grid.Bind(wxpg.EVT_PG_SELECTED, self._on_prop_selected)

    def show_record(self, session: EditorSession, path: Optional[str]) -> None:
        self._session = session
        self._record_path = path
        page = self.grid.GetPage(0)
        page.Clear()
        self.detail.SetLabel(" ")
        if not path or session is None:
            self.grid.RefreshGrid()
            return

        for child_path in _nodes.child_paths(session.working, path):
            value_at_path = _paths.get_path(session.working, child_path)
            kind = _nodes.classify(value_at_path)
            if kind in ("record", "collection"):
                continue
            node = api.get_node(session, child_path)
            # For a collection's own items, child_path is "path[i]" (no dot
            # separator) -- strip the shared prefix so rows read "[0]",
            # "[1]", ... instead of repeating the collection's own name.
            label = child_path[len(path):] if child_path.startswith(path) else child_path.rsplit(".", 1)[-1]
            prop = self._make_property(label, child_path, kind, node)
            if prop is None:
                continue
            page.Append(prop)
            help_bits = [f"evidence: {node.summary.evidence}"]
            if node.summary.label:
                help_bits.insert(0, f"command: {node.summary.label}")
            page.SetPropertyHelpString(prop, "; ".join(help_bits))
        self.grid.RefreshGrid()

    def _make_property(self, label: str, path: str, kind: str, node: _nodes.Node):
        value = node.value
        if kind == "scalar":
            wire_type = node.raw.wire_type
            if wire_type == "f32":
                return wxpg.FloatProperty(label, path, float(value))
            prop = wxpg.UIntProperty(label, path, int(value))
            if wire_type.startswith("bitset") or _looks_like_key(label):
                prop.SetAttribute(wxpg.PG_UINT_BASE, wxpg.PG_BASE_HEX)
                prop.SetAttribute(wxpg.PG_UINT_PREFIX, wxpg.PG_PREFIX_0x)
            return prop
        if kind == "string":
            return wxpg.StringProperty(label, path, value or "")
        if kind == "value":
            return wxpg.StringProperty(label, path, self._format_value(value))
        return None

    @staticmethod
    def _format_value(value) -> str:
        if isinstance(value, Vec2):
            return f"{value.x:g}, {value.y:g}"
        if isinstance(value, Vec3):
            return f"{value.x:g}, {value.y:g}, {value.z:g}"
        if isinstance(value, Bounds2):
            return f"{value.minimum.x:g}, {value.minimum.y:g} / {value.maximum.x:g}, {value.maximum.y:g}"
        if isinstance(value, Bounds3):
            return (
                f"{value.minimum.x:g}, {value.minimum.y:g}, {value.minimum.z:g} / "
                f"{value.maximum.x:g}, {value.maximum.y:g}, {value.maximum.z:g}"
            )
        return str(value)

    @staticmethod
    def _parse_value(text: str, template):
        nums = [float(p.strip()) for chunk in text.split("/") for p in chunk.split(",")]
        if isinstance(template, Vec2):
            return Vec2(nums[0], nums[1])
        if isinstance(template, Vec3):
            return Vec3(nums[0], nums[1], nums[2])
        if isinstance(template, Bounds2):
            return Bounds2(Vec2(nums[0], nums[1]), Vec2(nums[2], nums[3]))
        if isinstance(template, Bounds3):
            return Bounds3(Vec3(nums[0], nums[1], nums[2]), Vec3(nums[3], nums[4], nums[5]))
        raise ValueError("unsupported composite value")

    def _on_prop_changed(self, event: wxpg.PropertyGridEvent) -> None:
        prop = event.GetProperty()
        path = prop.GetName()
        current = _paths.get_path(self._session.working, path)
        kind = _nodes.classify(current)
        raw_value = prop.GetValue()

        if kind == "value":
            try:
                new_value = self._parse_value(raw_value, current)
            except (ValueError, IndexError):
                wx.MessageBox(
                    "Could not parse value; expected comma-separated numbers.",
                    "Invalid value",
                    wx.OK | wx.ICON_WARNING,
                )
                self.show_record(self._session, self._record_path)
                return
        elif kind == "scalar":
            wire_type = current.wire_type if isinstance(current, Raw) else ("f32" if isinstance(current, float) else "u32")
            new_value = float(raw_value) if wire_type == "f32" else int(raw_value)
        else:
            new_value = raw_value

        api.set_raw(self._session, path, new_value)
        self._on_change(path)

    def _on_prop_selected(self, event: wxpg.PropertyGridEvent) -> None:
        prop = event.GetProperty()
        if prop is None or self._session is None:
            self.detail.SetLabel(" ")
            return
        path = prop.GetName()
        node = api.get_node(self._session, path)
        bits = []
        if node.raw is not None:
            bits.append(f"wire: {node.raw.wire_type}")
        bits.append(f"evidence: {node.summary.evidence}")
        if node.summary.label:
            bits.append(f"binding: {node.summary.label}")
        self.detail.SetLabel(f"{path}   —   " + "   ·   ".join(bits))
