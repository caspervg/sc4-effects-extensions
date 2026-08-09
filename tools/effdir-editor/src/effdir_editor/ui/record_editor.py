"""Record editor: a property grid over one record's fields.

Scalar, vector, and nested record fields are shown inline. Shows binding
label + evidence as help text, and a detail strip for path/wire-type/evidence, per
effdir-editor-spec.md's "Field presentation".
"""

from __future__ import annotations

from dataclasses import is_dataclass
from typing import Callable, Optional

import wx
import wx.propgrid as wxpg

from ..bindings.bitfields import named_bits
from ..editor import api
from ..editor.curves import curve_info
from ..editor import nodes as _nodes
from ..editor import paths as _paths
from ..editor.references import (
    ReferenceIndex,
    build_reference_index,
    reference_info,
    reference_kind,
)
from ..editor.session import EditorSession
from ..model.decal import DecalDescriptor, effective_flags, effective_repeat_mode
from ..wire import Bounds2, Bounds3, Raw, Vec2, Vec3, WireString, WireVector
from .curve_view import edit_curve_dialog

_KEY_LABEL_SUBSTRINGS = ("key", "_id")

_FIELD_LABELS = {
    # Serialized and copied, but no text-parser setter or runtime read was
    # found in the symbolized Mac build. Keep the offset-bearing model names
    # while qualifying their editor labels rather than declaring padding.
    ("ParticleDescriptor", "value_164"): "value_164 (unused?)",
    ("ParticleDescriptor", "value_166"): "value_166 (unused?)",
    ("ParticleDescriptor", "value_168"): "value_168 (unused?)",
    ("DynamicParticleDescriptor", "flags"): "flags (unused in shipped runtime)",
    ("DynamicParticleDescriptor", "value_14"): "unused_14 (stored float)",
    ("DynamicParticleDescriptor", "value_24"): "unused_24 (stored float)",
    ("DecalDescriptor", "flags"): "flags (stored)",
    ("DecalDescriptor", "repeat_mode"): "repeat_mode (stored)",
    ("ScrubberDescription", "value_10"): "value_10 (unused?)",
    ("EventRecord", "name"): "definition_name",
    ("EventRecord", "time"): "epicenter_radius (flash only)",
    ("EventRecord", "value"): "resolved_description_index",
    ("AttractorDescription", "name"): "Lua reference",
    ("AttractorDescription", "selector"): "Type",
}

# Scalar fields confirmed (not guessed) to be two-state, rendered as a
# checkbox instead of a numeric field. A starter set -- see catalog.py's
# own "starter set, not the full table" policy -- grow it only as more
# fields get the same level of confirmation, not from "value is 0 or 1 in
# one sample file" alone (many value_XX placeholders happen to be 0/1 in a
# given file without that being their full valid range).
_BOOLEAN_FIELDS = {
    # gates trailing_float_metadata's optional tail; model/resource.py's
    # reader/writer branch on `!= 0`, so this is a code-level fact, not a
    # guess.
    ("TrailingFloatMetadata", "present"),
}

_ENUM_FIELDS = {
    ("AttractorDescription", "selector"): (
        ["Attractor / generator", "Occupant group"],
        [0, 1],
    ),
    ("ShakeDescriptor", "base_table"): (
        ["Random (two-axis)", "Sine Y (vertical)"],
        [0, 1],
    ),
}

_FIELD_HELP = {
    ("DynamicParticleDescriptor", "flags"): (
        "preserved bitset with no registered text setter or runtime read in "
        "the paired shipped Mac/Windows implementations; all vanilla records store zero"
    ),
    ("DynamicParticleDescriptor", "value_14"): (
        "preserved float at object offset +0x14; initialized and stored as "
        "zero in every vanilla record, with no text setter or runtime read "
        "in the paired shipped builds"
    ),
    ("DynamicParticleDescriptor", "value_24"): (
        "preserved float at object offset +0x24; initialized and stored as "
        "zero in every vanilla record, with no text setter or runtime read "
        "in the paired shipped builds"
    ),
    ("DecalDescriptor", "flags"): (
        "stored bitset; when repeat_mode is stored as 0 the game derives "
        "the static bit (bit 6) without changing this wire value"
    ),
    ("DecalDescriptor", "repeat_mode"): (
        "stored wire byte; the game normalizes stored 0 to effective mode 2"
    ),
}

_HEX_FIELDS = {
    # These are SC4 message identifiers rather than ordinary decimal counts.
    ("EffectDescription", "start_message_1"),
    ("EffectDescription", "start_message_2"),
    ("EffectDescription", "start_message_3"),
    ("ScrubberDescription", "message_1"),
    ("ScrubberDescription", "message_2"),
    ("MessageTrigger", "message_id"),
    # Effect-key map entries contain resource-style group/instance IDs.
    ("StringU32U32Record", "group_id"),
    ("StringU32U32Record", "instance_id"),
}

# Confirmed normalized-float RGB curves. Restrict swatches to these paths;
# arbitrary Vec3 fields are positions, forces, directions, or dimensions.
_COLOR_VECTOR_FIELDS = {
    ("ParticleDescriptor", "color_curve"),
    ("DecalDescriptor", "color"),
    ("LightDescriptor", "color"),
}

# wxPython's propgrid stubs export this as ``ReadOnly``, but some installed
# runtimes only expose it through the PGFlags enum.
_PG_READ_ONLY = getattr(
    getattr(wxpg, "PGFlags", object()),
    "ReadOnly",
    getattr(wxpg, "ReadOnly", 1 << 15),
)

def _looks_like_key(label: str) -> bool:
    """SC4 resource keys, message/group/instance IDs, etc. are
    conventionally shown in hex across SC4 modding tools."""

    lowered = label.lower()
    if lowered.startswith("marker"):
        return False
    return any(s in lowered for s in _KEY_LABEL_SUBSTRINGS)


class RecordEditor(wx.Panel):
    def __init__(self, parent, on_change: Callable[[str], None], on_navigate: Optional[Callable[[str], None]] = None):
        super().__init__(parent)
        self._session: Optional[EditorSession] = None
        self._record_path: Optional[str] = None
        self._on_change = on_change
        self._on_navigate = on_navigate
        self._references: list = []
        self._outgoing_references: list = []
        self._reference_rows: list = []
        self._reference_index: Optional[ReferenceIndex] = None
        self._bit_parent_properties: dict[str, wxpg.PGProperty] = {}
        self._color_preview_properties: dict[str, wxpg.PGProperty] = {}
        self._ui_property_data: dict[str, tuple] = {}

        self.reference_splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        self.editor_panel = wx.Panel(self.reference_splitter)
        self.references_panel = wx.Panel(self.reference_splitter)
        self.reference_splitter.SetMinimumPaneSize(self.FromDIP(96))

        self.header = wx.Panel(self.editor_panel)
        self.header.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE))
        self.record_title = wx.StaticText(self.header, label="Select a record")
        title_font = self.record_title.GetFont()
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self.record_title.SetFont(title_font)
        self.record_meta = wx.StaticText(self.header, label="")
        self.record_meta.SetFont(self.record_meta.GetFont().Smaller())
        self.record_status = wx.StaticText(self.header, label="Ready")
        self.record_status.SetFont(self.record_status.GetFont().Smaller())
        header_layout = wx.BoxSizer(wx.HORIZONTAL)
        header_text = wx.BoxSizer(wx.VERTICAL)
        header_text.Add(self.record_title, 0, wx.EXPAND)
        header_text.Add(self.record_meta, 0, wx.EXPAND | wx.TOP, self.FromDIP(2))
        header_layout.Add(header_text, 1, wx.EXPAND)
        header_layout.Add(self.record_status, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.FromDIP(8))
        self.header.SetSizer(header_layout)

        self.field_filter = wx.SearchCtrl(self.editor_panel, style=wx.TE_PROCESS_ENTER)
        self.field_filter.SetDescriptiveText("Filter fields by name or path")
        self.field_filter.ShowCancelButton(True)
        self.filter_status = wx.StaticText(self.editor_panel, label="")
        self.filter_status.SetFont(self.filter_status.GetFont().Smaller())

        self.grid = wxpg.PropertyGridManager(
            self.editor_panel,
            style=wxpg.PG_SPLITTER_AUTO_CENTER | wxpg.PGMAN_DEFAULT_STYLE | wxpg.PG_TOOLTIPS,
        )
        self.grid.AddPage("Fields")
        self.grid.SetColumnCount(3)
        self.grid.SetColumnTitle(0, "Field")
        self.grid.SetColumnTitle(1, "Value")
        self.grid.SetColumnTitle(2, "Info")
        self.grid.SetColumnProportion(0, 44)
        self.grid.SetColumnProportion(1, 36)
        self.grid.SetColumnProportion(2, 20)
        # wx requires PG_SPLITTER_AUTO_CENTER while proportions are set. Keep
        # the initial proportions, then disable the resize behaviour that
        # would otherwise move the splitter back to the centre.
        self.grid.SetWindowStyleFlag(
            self.grid.GetWindowStyleFlag() & ~wxpg.PG_SPLITTER_AUTO_CENTER
        )
        self.detail = wx.StaticText(self.editor_panel, label=" ")
        self.detail.SetFont(self.detail.GetFont().Smaller())

        self.references_label = wx.StaticText(self.references_panel, label="References · 0 in · 0 out")
        reference_font = self.references_label.GetFont()
        reference_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self.references_label.SetFont(reference_font)
        self.references_list = wx.ListCtrl(
            self.references_panel,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES | wx.LC_VRULES,
        )
        self.references_list.InsertColumn(0, "Direction", width=self.FromDIP(72))
        self.references_list.InsertColumn(1, "Kind", width=self.FromDIP(120))
        self.references_list.InsertColumn(2, "Path", width=self.FromDIP(300))
        self.references_list.InsertColumn(3, "Info", width=self.FromDIP(520))
        self.references_list.SetMinSize(self.FromDIP((-1, 96)))

        editor_sizer = wx.BoxSizer(wx.VERTICAL)
        editor_sizer.Add(self.header, 0, wx.EXPAND | wx.ALL, self.FromDIP(6))
        filter_row = wx.BoxSizer(wx.HORIZONTAL)
        filter_row.Add(self.field_filter, 1, wx.EXPAND)
        filter_row.Add(self.filter_status, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.FromDIP(8))
        editor_sizer.Add(filter_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.FromDIP(6))
        editor_sizer.Add(self.grid, 1, wx.EXPAND)
        editor_sizer.Add(self.detail, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, self.FromDIP(6))
        self.editor_panel.SetSizer(editor_sizer)

        references_sizer = wx.BoxSizer(wx.VERTICAL)
        references_sizer.Add(self.references_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, self.FromDIP(6))
        references_sizer.Add(self.references_list, 1, wx.EXPAND | wx.ALL, self.FromDIP(6))
        self.references_panel.SetSizer(references_sizer)

        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(self.reference_splitter, 1, wx.EXPAND)
        self.SetSizer(root_sizer)
        self._show_references(False)

        self.grid.Bind(wxpg.EVT_PG_CHANGED, self._on_prop_changed)
        self.grid.Bind(wxpg.EVT_PG_SELECTED, self._on_prop_selected)
        self.grid.GetGrid().Bind(wx.EVT_LEFT_DCLICK, self._on_grid_double_click)
        self.field_filter.Bind(wx.EVT_TEXT, self._on_field_filter)
        self.field_filter.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_field_filter_cancel)
        self.references_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_reference_activated)
        self.references_list.Bind(wx.EVT_CONTEXT_MENU, self._on_reference_context)
        self.references_list.Bind(wx.EVT_SIZE, self._on_references_size)

    def show_record(self, session: EditorSession, path: Optional[str]) -> None:
        if path and isinstance(_paths.get_path(session.working, path), WireVector):
            self.show_collection(session, path)
            return

        self._session = session
        self._record_path = path
        page = self.grid.GetPage(0)
        page.Clear()
        self._bit_parent_properties.clear()
        self._color_preview_properties.clear()
        self._ui_property_data.clear()
        self.detail.SetLabel(" ")
        self._reset_field_filter()
        if not path or session is None:
            self.grid.RefreshGrid()
            self._show_references(False)
            self._set_record_header(None, None)
            return

        self._reference_index = build_reference_index(session.working)
        record_node = api.get_node(session, path, reference_index=self._reference_index)
        self._references = record_node.referenced_by
        self._outgoing_references = record_node.references
        self._set_reference_rows(self._references, self._outgoing_references)
        self._show_references(True)
        self._set_record_header(record_node, path)

        group_index = 0
        for child_path in _nodes.child_paths(session.working, path):
            value_at_path = _paths.get_path(session.working, child_path)
            kind = _nodes.classify(value_at_path)
            node = api.get_node(session, child_path, reference_index=self._reference_index)
            # For a collection's own items, child_path is "path[i]" (no dot
            # separator) -- strip the shared prefix so rows read "[0]",
            # "[1]", ... instead of repeating the collection's own name.
            label = child_path[len(path):] if child_path.startswith(path) else child_path.rsplit(".", 1)[-1]
            label = _FIELD_LABELS.get((self._parent_record_type(child_path), label), label)
            if kind == "collection":
                prop = self._make_vector_property(label, child_path, value_at_path, page)
            else:
                prop = self._make_property(label, child_path, kind, node)
            if prop is None:
                continue
            self._register_property(prop, child_path)
            if kind == "collection":
                # _make_vector_property owns insertion because it also adds
                # the vector's expandable element rows.
                pass
            else:
                page.Append(prop)
                if kind == "record":
                    prop.ChangeFlag(_PG_READ_ONLY, True)
                    prop.SetExpanded(False)
                    self._add_record_children(page, prop, child_path)
                if node.raw is not None and node.raw.wire_type.startswith("bitset<"):
                    self._add_bitset_children(page, prop, child_path, node.raw.wire_type, int(node.value))
            page.SetPropertyHelpString(prop, self._property_help(node, child_path, kind))
            self._set_semantic_preview(prop, child_path)
            # Zebra-strip top-level properties, and let expandable children
            # inherit the exact same tint as their parent block.
            self.grid.SetPropertyBackgroundColour(prop, self._property_group_colour(group_index))
            group_index += 1
        # SetPropertyBackgroundColour recurses by default, so the zebra pass
        # above overwrites custom descendant cell backgrounds. Apply swatches
        # last, after all top-level block colours are final.
        self._refresh_color_previews()
        self._apply_field_filter()
        self.grid.RefreshGrid()

    def show_collection(self, session: EditorSession, path: str) -> None:
        self._session = session
        self._record_path = path
        self._reference_index = None
        self._references = []
        self._outgoing_references = []
        page = self.grid.GetPage(0)
        page.Clear()
        self._bit_parent_properties.clear()
        self._color_preview_properties.clear()
        self._ui_property_data.clear()
        self._reset_field_filter()
        self._set_reference_rows([], [])
        self._show_references(False)
        self._set_record_header(None, path)

        collection = _paths.get_path(session.working, path)
        count = len(collection.items) if isinstance(collection, WireVector) else 0
        prop = wxpg.StringProperty("Items", path, f"{count} items")
        property_data = ("path", path)
        prop.SetClientData(property_data)
        self._ui_property_data[path] = property_data
        prop.ChangeFlag(_PG_READ_ONLY, True)
        page.Append(prop)
        page.SetPropertyHelpString(prop, "Select an individual entry in the tree to inspect or edit it")
        self.detail.SetLabel(f"{path}   —   collection with {count} items")
        self._apply_field_filter()
        self.grid.RefreshGrid()

    def _add_record_children(self, page, parent, path: str) -> None:
        """Recursively expose a dataclass record beneath a property row."""

        for child_path in _nodes.child_paths(self._session.working, path):
            value = _paths.get_path(self._session.working, child_path)
            kind = _nodes.classify(value)
            node = api.get_node(self._session, child_path, reference_index=self._reference_index)
            label = child_path.rsplit(".", 1)[-1]
            label = _FIELD_LABELS.get((self._parent_record_type(child_path), label), label)

            if kind == "collection":
                self._make_vector_property(label, child_path, value, page, parent=parent)
                continue

            child = self._make_property(label, child_path, kind, node)
            if child is None:
                continue
            property_data = ("path", child_path)
            child.SetClientData(property_data)
            self._ui_property_data[child_path] = property_data
            page.AppendIn(parent, child)
            page.SetPropertyHelpString(child, self._property_help(node, child_path, kind))
            self._set_semantic_preview(child, child_path)
            if kind == "record":
                child.ChangeFlag(_PG_READ_ONLY, True)
                child.SetExpanded(False)
                self._add_record_children(page, child, child_path)
            elif node.raw is not None and node.raw.wire_type.startswith("bitset<"):
                self._add_bitset_children(page, child, child_path, node.raw.wire_type, int(node.value))

    def _parent_record_type(self, path: str) -> Optional[str]:
        parent_path = _paths.parent_path(path)
        parent_value = _paths.get_path(self._session.working, parent_path) if parent_path else self._session.working
        return type(parent_value).__name__

    def _property_help(self, node: _nodes.Node, path: str, kind: str) -> str:
        """Build user-facing help from the binding catalog and wire context."""

        parts = []
        if kind == "collection":
            parts.append("expand to inspect/edit vector elements")
            if curve_info(node) is not None:
                parts.append("double-click to open the curve editor")
        elif kind == "record":
            parts.append("expand to inspect/edit nested fields")

        commands = list(dict.fromkeys(binding.command_path for binding in node.bindings))
        if commands:
            parts.append(f"command: {', '.join(commands)}")
        parts.append(f"evidence: {node.summary.evidence}")

        tokens = _paths.tokenize(path)
        attr_name = tokens[-1] if tokens and isinstance(tokens[-1], str) else None
        record_type = self._parent_record_type(path)
        field_help = _FIELD_HELP.get((record_type, attr_name)) if attr_name else None
        if field_help:
            parts.append(field_help)

        for note in dict.fromkeys(binding.notes for binding in node.bindings if binding.notes):
            parts.append(note)
        transforms = list(
            dict.fromkeys(
                transform.description
                for binding in node.bindings
                for transform in binding.transforms
            )
        )
        if transforms:
            parts.append(f"transform: {', '.join(transforms)}")
        runtime_refs = list(
            dict.fromkeys(
                ref.address
                for binding in node.bindings
                for ref in binding.runtime_refs
            )
        )
        if runtime_refs:
            parts.append(f"runtime: {', '.join(runtime_refs)}")
        return "; ".join(parts)

    def _semantic_preview(self, path: str) -> Optional[str]:
        tokens = _paths.tokenize(path)
        if not tokens or not isinstance(tokens[-1], str):
            return None
        record_path = _paths.parent_path(path)
        record = _paths.get_path(self._session.working, record_path)
        if not isinstance(record, DecalDescriptor):
            return None
        if tokens[-1] == "repeat_mode":
            return f"effective {effective_repeat_mode(record)}"
        if tokens[-1] == "flags":
            return f"effective {self._format_hex(effective_flags(record))}"
        return None

    def _set_semantic_preview(self, prop: wxpg.PGProperty, path: str) -> None:
        preview = self._semantic_preview(path)
        if preview is not None:
            self.grid.SetPropertyCell(prop, 2, preview)

    def _make_property(
        self,
        label: str,
        path: str,
        kind: str,
        node: _nodes.Node,
        *,
        property_name: Optional[str] = None,
    ):
        property_name = property_name or path
        value = node.value
        if kind == "scalar":
            wire_type = node.raw.wire_type
            if wire_type == "f32":
                return wxpg.FloatProperty(label, property_name, float(value))
            if wire_type.startswith("bitset<"):
                return self._make_bitset_property(label, property_name, wire_type, int(value))
            attr_name = _paths.tokenize(path)[-1]
            record_type = self._parent_record_type(path)
            enum = _ENUM_FIELDS.get((record_type, attr_name)) if isinstance(attr_name, str) else None
            if enum is not None:
                choices, values = enum
                return wxpg.EnumProperty(label, property_name, choices, values, int(value))
            if isinstance(attr_name, str) and (self._parent_record_type(path), attr_name) in _BOOLEAN_FIELDS:
                prop = wxpg.BoolProperty(label, property_name, bool(value))
                prop.SetAttribute(wxpg.PG_BOOL_USE_CHECKBOX, True)
                return prop
            prop = wxpg.UIntProperty(label, property_name, int(value))
            attr_name = _paths.tokenize(path)[-1]
            record_type = self._parent_record_type(path)
            if (
                isinstance(attr_name, str)
                and (record_type, attr_name) in _HEX_FIELDS
            ) or _looks_like_key(label):
                prop.SetAttribute(wxpg.PG_UINT_BASE, wxpg.PG_BASE_HEX)
                prop.SetAttribute(wxpg.PG_UINT_PREFIX, wxpg.PG_PREFIX_0x)
            return prop
        if kind == "string":
            return wxpg.StringProperty(label, property_name, value or "")
        if kind == "value":
            return wxpg.StringProperty(label, property_name, self._format_value(value))
        if kind == "record":
            return wxpg.StringProperty(label, property_name, type(value).__name__)
        return None

    def _make_bitset_property(
        self,
        label: str,
        path: str,
        wire_type: str,
        value: int,
    ) -> wxpg.PGProperty:
        bit_count = int(wire_type[len("bitset<") : -1])
        return wxpg.StringProperty(label, path, self._format_hex(value))

    def _add_bitset_children(self, page, parent, path: str, wire_type: str, value: int) -> None:
        """Render every known/unknown bit as an inline checkbox.

        The read-only hex row is intentionally a separate child so the
        checked state remains the primary representation while the original
        packed value stays visible for SC4-oriented debugging.
        """

        parent.ChangeFlag(_PG_READ_ONLY, True)
        self._bit_parent_properties[path] = parent
        parent.SetExpanded(True)
        bit_count = int(wire_type[len("bitset<") : -1])
        attr_name = _paths.tokenize(path)[-1]
        record_type = self._parent_record_type(path)
        labels = named_bits(record_type, attr_name, bit_count) if isinstance(attr_name, str) else {}
        for bit, label in labels.items():
            bit_name = f"{path}.__bit_{bit}"
            checkbox = wxpg.BoolProperty(label, bit_name, bool(value & (1 << bit)))
            checkbox.SetAttribute(wxpg.PG_BOOL_USE_CHECKBOX, True)
            property_data = ("bit", path, bit)
            checkbox.SetClientData(property_data)
            self._ui_property_data[bit_name] = property_data
            page.AppendIn(parent, checkbox)
        if len(labels) < bit_count:
            unnamed_mask = value & ~sum(1 << bit for bit in labels)
            unnamed_name = f"{path}.__unnamed_bits"
            unnamed = wxpg.StringProperty("unnamed bits", unnamed_name, self._format_hex(unnamed_mask))
            unnamed.ChangeFlag(_PG_READ_ONLY, True)
            property_data = ("path", path)
            unnamed.SetClientData(property_data)
            self._ui_property_data[unnamed_name] = property_data
            page.AppendIn(parent, unnamed)

    def _make_vector_property(
        self,
        label: str,
        path: str,
        vector: WireVector,
        page,
        *,
        parent=None,
    ) -> wxpg.PGProperty:
        """Add a compact, expandable view of a wire vector to its parent.

        Scalar and fixed-shape vector elements reuse the normal editors, so
        curves such as ``shake.amplitude`` can be inspected and edited in
        place. Record elements get a read-only parent row whose own fields
        can be expanded and edited inline as well.
        """

        prop = wxpg.StringProperty(label, path, self._format_vector(vector))
        property_data = ("path", path)
        prop.SetClientData(property_data)
        self._ui_property_data[path] = property_data
        prop.SetExpanded(False)
        if parent is None:
            page.Append(prop)
        else:
            page.AppendIn(parent, prop)
        vector_node = api.get_node(self._session, path, reference_index=self._reference_index)
        page.SetPropertyHelpString(prop, self._property_help(vector_node, path, "collection"))
        if curve_info(vector_node) is not None:
            self.grid.SetPropertyCell(prop, 2, "Double-click to edit curve")
        prop.ChangeFlag(_PG_READ_ONLY, True)
        for index, item in enumerate(vector.items):
            child_path = f"{path}[{index}]"
            property_name = self._vector_property_name(path, index)
            child_node = api.get_node(self._session, child_path, reference_index=self._reference_index)
            child_kind = _nodes.classify(item)
            child = self._make_property(
                f"[{index}]",
                child_path,
                child_kind,
                child_node,
                property_name=property_name,
            )
            if child is None:
                child = wxpg.StringProperty(f"[{index}]", property_name, self._format_item(item))
            property_data = ("path", child_path)
            child.SetClientData(property_data)
            self._ui_property_data[property_name] = property_data
            if self._vector_uses_hex(path) and child_kind == "scalar":
                child.SetAttribute(wxpg.PG_UINT_BASE, wxpg.PG_BASE_HEX)
                child.SetAttribute(wxpg.PG_UINT_PREFIX, wxpg.PG_PREFIX_0x)
            page.AppendIn(prop, child)
            if self._vector_is_color(path) and isinstance(item, Vec3):
                self._color_preview_properties[child_path] = child
                self._set_color_preview_cell(child, item)
            if child_kind == "record" or child_kind == "collection":
                child.ChangeFlag(_PG_READ_ONLY, True)
            if child_kind == "record":
                child.SetExpanded(False)
                self._add_record_children(page, child, child_path)
        return prop

    def _property_group_colour(self, group_index: int) -> wx.Colour:
        """Return a theme-aware zebra tint for one top-level property block."""

        base = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
        if group_index % 2 == 0:
            return base
        target = wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
        blend = 0.06
        return wx.Colour(
            int(base.Red() * (1.0 - blend) + target.Red() * blend),
            int(base.Green() * (1.0 - blend) + target.Green() * blend),
            int(base.Blue() * (1.0 - blend) + target.Blue() * blend),
        )

    @staticmethod
    def _vector_property_name(path: str, index: int) -> str:
        """Create a UI-only name that wx won't reinterpret as a model path."""

        safe_path = path.replace(".", "_").replace("[", "_").replace("]", "")
        return f"__vector_{safe_path}_{index}"

    @staticmethod
    def _format_hex(value: int) -> str:
        return f"0x{value:08X}"

    def _vector_uses_hex(self, path: str) -> bool:
        tokens = _paths.tokenize(path)
        if not tokens or not isinstance(tokens[-1], str):
            return False
        record_path = _paths.parent_path(path)
        record = _paths.get_path(self._session.working, record_path) if record_path else self._session.working
        return (type(record).__name__, tokens[-1]) in {
            ("ParticleDescriptor", "model_keys"),
            ("DynamicParticleDescriptor", "model_keys"),
        }

    def _vector_is_color(self, path: str) -> bool:
        tokens = _paths.tokenize(path)
        if not tokens or not isinstance(tokens[-1], str):
            return False
        record_path = _paths.parent_path(path)
        record = _paths.get_path(self._session.working, record_path) if record_path else self._session.working
        return (type(record).__name__, tokens[-1]) in _COLOR_VECTOR_FIELDS

    @staticmethod
    def _color_channels(value: Vec3) -> tuple[int, int, int]:
        def channel(component: float) -> int:
            return max(0, min(255, round(float(component) * 255.0)))

        return channel(value.x), channel(value.y), channel(value.z)

    @classmethod
    def _color_hex(cls, value: Vec3) -> str:
        red, green, blue = cls._color_channels(value)
        return f"#{red:02X}{green:02X}{blue:02X}"

    @classmethod
    def _color_colour(cls, value: Vec3) -> wx.Colour:
        return wx.Colour(*cls._color_channels(value))

    def _set_color_preview_cell(self, prop: wxpg.PGProperty, value: Vec3) -> None:
        colour = self._color_colour(value)
        luminance = 0.2126 * colour.Red() + 0.7152 * colour.Green() + 0.0722 * colour.Blue()
        self.grid.SetPropertyCell(
            prop,
            2,
            self._color_hex(value),
            fgCol=wx.BLACK if luminance >= 140 else wx.WHITE,
            bgCol=colour,
        )

    def _refresh_color_previews(self) -> None:
        for path, prop in self._color_preview_properties.items():
            value = _paths.get_path(self._session.working, path)
            if isinstance(value, Vec3):
                self._set_color_preview_cell(prop, value)

    @classmethod
    def _format_vector(cls, vector: WireVector) -> str:
        if not vector.items:
            return "0 items"
        preview = ", ".join(cls._format_item(item, bracket_composites=True) for item in vector.items[:4])
        if len(vector.items) > 4:
            preview += ", …"
        return f"{len(vector.items)} items: {preview}"

    @classmethod
    def _format_item(cls, item, *, bracket_composites: bool = False) -> str:
        if isinstance(item, Raw):
            return cls._format_item(item.value, bracket_composites=bracket_composites)
        if isinstance(item, WireString):
            return item.decoded or "<raw string>"
        if isinstance(item, (Vec2, Vec3, Bounds2, Bounds3)):
            formatted = cls._format_value(item)
            return f"[{formatted}]" if bracket_composites else formatted
        if is_dataclass(item):
            return type(item).__name__
        if isinstance(item, float):
            return f"{item:g}"
        return str(item)

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
        client_data = self._property_data(prop)
        if isinstance(client_data, tuple) and client_data and client_data[0] == "bit":
            _, path, bit = client_data
            current = _paths.get_path(self._session.working, path)
            new_value = current.value | (1 << bit) if bool(prop.GetValue()) else current.value & ~(1 << bit)
            api.set_raw(self._session, path, new_value)
            self._refresh_bitset_properties(path)
            self._refresh_semantic_previews(path)
            self._refresh_record_header()
            self._on_change(path)
            return
        path = client_data[1] if isinstance(client_data, tuple) and client_data and client_data[0] == "path" else prop.GetName()
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
        self._refresh_vector_summary(path)
        self._refresh_semantic_previews(path)
        self._refresh_record_header()
        self._on_change(path)

    def _refresh_bitset_properties(self, path: str) -> None:
        raw = _paths.get_path(self._session.working, path)
        if not isinstance(raw, Raw):
            return
        value = int(raw.value)
        parent = self._bit_parent_properties.get(path)
        if parent is not None:
            parent.SetValue(self._format_hex(value))

    def _refresh_semantic_previews(self, changed_path: str) -> None:
        """Refresh both derived decal cells when either source field changes."""

        record_path = _paths.parent_path(changed_path)
        record = _paths.get_path(self._session.working, record_path)
        if not isinstance(record, DecalDescriptor):
            return
        for attr_name in ("flags", "repeat_mode"):
            path = f"{record_path}.{attr_name}"
            prop = self.grid.GetPropertyByName(path)
            if prop is not None:
                self._set_semantic_preview(prop, path)

    def _refresh_vector_summary(self, path: str) -> None:
        """Keep an expanded vector's parent preview current after an edit."""

        tokens = _paths.tokenize(path)
        if not tokens or not isinstance(tokens[-1], int):
            return
        vector_path = _paths.parent_path(path)
        vector = _paths.get_path(self._session.working, vector_path)
        if not isinstance(vector, WireVector):
            return
        prop = self.grid.GetPropertyByName(vector_path)
        if prop is not None:
            prop.SetValue(self._format_vector(vector))
        if self._vector_is_color(vector_path):
            for index, item in enumerate(vector.items):
                if not isinstance(item, Vec3):
                    continue
                child = self.grid.GetPropertyByName(self._vector_property_name(vector_path, index))
                if child is None:
                    continue
                self._set_color_preview_cell(child, item)

    def _on_grid_double_click(self, event: wx.MouseEvent) -> None:
        """Open a colour picker for a double-click in a preview cell.

        wx's semantic property-double-click event is geared towards the
        editable value column and does not reliably identify custom columns.
        A mouse hit test on the underlying PropertyGrid preserves the actual
        clicked column.
        """

        hit = self.grid.GetGrid().HitTest(event.GetPosition())
        prop = hit.GetProperty()
        if prop is None or self._session is None:
            event.Skip()
            return
        client_data = self._property_data(prop)
        if not (isinstance(client_data, tuple) and client_data and client_data[0] == "path"):
            path = prop.GetName()
        else:
            path = client_data[1]
        current = _paths.get_path(self._session.working, path)

        curve_path = path
        selected = -1
        tokens = _paths.tokenize(path)
        if tokens and isinstance(tokens[-1], int):
            selected = tokens[-1]
            curve_path = _paths.parent_path(path)
        try:
            curve_node = api.get_node(self._session, curve_path)
        except (AttributeError, IndexError, KeyError, ValueError):
            curve_node = None
        curve = curve_info(curve_node) if curve_node is not None else None
        if curve is not None:
            self._open_curve_editor(curve_path, curve, selected)
            return

        if hit.GetColumn() != 2:
            event.Skip()
            return
        vector_path = _paths.parent_path(path)
        if not isinstance(current, Vec3) or not self._vector_is_color(vector_path):
            event.Skip()
            return

        colour_data = wx.ColourData()
        colour_data.SetColour(self._color_colour(current))
        colour_data.SetChooseFull(True)
        with wx.ColourDialog(self, colour_data) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            colour = dialog.GetColourData().GetColour()
            # Copy primitives while the native dialog and its ColourData are
            # still alive. Do not retain a wx wrapper owned by the dialog.
            red, green, blue = colour.Red(), colour.Green(), colour.Blue()

        new_value = Vec3(red / 255.0, green / 255.0, blue / 255.0)
        api.set_raw(self._session, path, new_value)
        prop.SetValue(self._format_value(new_value))
        self._set_color_preview_cell(prop, new_value)
        self._refresh_vector_summary(path)
        self._refresh_record_header()
        # MainFrame's callback refreshes the resource tree and may rebuild the
        # property page. Defer that work until wx has finished dispatching the
        # native double-click event that owns ``prop``.
        wx.CallAfter(self._on_change, path)

    def _open_curve_editor(self, path: str, info, selected: int = -1) -> None:
        if self._session is None:
            return
        vector = _paths.get_path(self._session.working, path)
        if not isinstance(vector, WireVector):
            return
        values = edit_curve_dialog(
            self,
            f"Edit curve — {path}",
            path,
            info.commands,
            vector.items,
            selected=selected,
        )
        if values is None or values == list(vector.items):
            return

        updated = WireVector(count=len(values), items=list(values), source_span=vector.source_span)
        api.set_raw(self._session, path, updated)
        parent = self.grid.GetPropertyByName(path)
        if parent is not None:
            parent.SetValue(self._format_vector(updated))
        for index, value in enumerate(values):
            child = self.grid.GetPropertyByName(self._vector_property_name(path, index))
            if child is not None:
                child.SetValue(value)
        self._refresh_record_header()
        self.grid.RefreshGrid()
        self._on_change(path)

    def _on_prop_selected(self, event: wxpg.PropertyGridEvent) -> None:
        prop = event.GetProperty()
        if prop is None or self._session is None:
            self.detail.SetLabel(" ")
            return
        client_data = self._property_data(prop)
        path = client_data[1] if isinstance(client_data, tuple) and client_data and client_data[0] in ("path", "bit") else prop.GetName()
        node = api.get_node(self._session, path)
        bits = []
        if node.raw is not None:
            bits.append(f"wire: {node.raw.wire_type}")
        bits.append(f"evidence: {node.summary.evidence}")
        if node.summary.label:
            bits.append(f"binding: {node.summary.label}")
        runtime_refs = list(
            dict.fromkeys(ref.address for binding in node.bindings for ref in binding.runtime_refs)
        )
        if runtime_refs:
            bits.append(f"runtime: {', '.join(runtime_refs)}")
        notes = list(dict.fromkeys(binding.notes for binding in node.bindings if binding.notes))
        if notes:
            bits.append(notes[0])
        self.detail.SetLabel(f"{path}   —   " + "   ·   ".join(bits))

    def _property_data(self, prop: wxpg.PGProperty):
        client_data = prop.GetClientData()
        if isinstance(client_data, tuple) and client_data and client_data[0] in ("path", "bit"):
            return client_data
        return self._ui_property_data.get(prop.GetName())

    def _register_property(self, prop: wxpg.PGProperty, path: str) -> None:
        if prop.GetClientData() is None:
            prop.SetClientData(("path", path))
        self._ui_property_data[prop.GetName()] = self._property_data(prop) or ("path", path)

    def _reset_field_filter(self) -> None:
        self.field_filter.ChangeValue("")
        self.filter_status.SetLabel("")

    def _on_field_filter(self, _event: wx.CommandEvent) -> None:
        self._apply_field_filter()

    def _on_field_filter_cancel(self, _event: wx.CommandEvent) -> None:
        self._reset_field_filter()
        self._apply_field_filter()

    @staticmethod
    def _is_path_parent(parent: str, child: str) -> bool:
        return child == parent or child.startswith(f"{parent}.") or child.startswith(f"{parent}[")

    def _apply_field_filter(self) -> None:
        page = self.grid.GetPage(0)
        query = self.field_filter.GetValue().strip().lower()
        entries = []
        for property_name, data in self._ui_property_data.items():
            if not isinstance(data, tuple) or len(data) < 2:
                continue
            prop = page.GetPropertyByName(property_name)
            if prop is None:
                continue
            path = data[1]
            entries.append((property_name, path, prop.GetLabel()))
        if not entries:
            self.filter_status.SetLabel("")
            return

        matching_paths = {
            path
            for _, path, label in entries
            if not query or query in f"{path} {label}".lower()
        }
        visible = 0
        for property_name, path, _label in entries:
            show = not query or any(self._is_path_parent(path, match) for match in matching_paths)
            page.HideProperty(property_name, not show)
            if show:
                visible += 1
        if query:
            self.filter_status.SetLabel(f"{visible} fields")
        else:
            self.filter_status.SetLabel(f"{len(entries)} fields")
        self.grid.RefreshGrid()

    def _set_record_header(self, node: Optional[_nodes.Node], path: Optional[str]) -> None:
        if path is not None and node is None and self._session is not None:
            self.record_title.SetLabel("Collection")
            self.record_meta.SetLabel(f"{path}   ·   collection")
            self.record_status.SetLabel("Ready")
            self.record_status.SetForegroundColour(
                wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
            )
            self.header.Layout()
            return
        if node is None or path is None or self._session is None:
            self.record_title.SetLabel("Select a record")
            self.record_meta.SetLabel("")
            self.record_status.SetLabel("Ready")
            self.record_status.SetForegroundColour(
                wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
            )
            return
        value = _paths.get_path(self._session.working, path)
        title = node.summary.display_name or type(value).__name__
        self.record_title.SetLabel(title)
        meta = f"{type(value).__name__}   ·   {path}"
        if node.summary.evidence:
            meta += f"   ·   {node.summary.evidence}"
        self.record_meta.SetLabel(meta)
        modified = self._session.dirty
        self.record_status.SetLabel("Modified" if modified else "Ready")
        self.record_status.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT)
            if modified
            else wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT)
        )
        self.header.Layout()

    def _refresh_record_header(self) -> None:
        if self._session is None or self._record_path is None:
            return
        node = api.get_node(self._session, self._record_path, reference_index=self._reference_index)
        self._set_record_header(node, self._record_path)

    def _set_reference_rows(self, incoming: list, outgoing: list) -> None:
        rows = [("In", reference) for reference in incoming]
        rows.extend(("Out", reference) for reference in outgoing)
        self._reference_rows = sorted(
            rows,
            key=lambda row: (0 if row[0] == "In" else 1, reference_kind(row[1]), row[1].path),
        )
        self.references_list.DeleteAllItems()
        self.references_label.SetLabel(
            f"References · {len(incoming)} in · {len(outgoing)} out"
        )
        if not self._reference_rows:
            row = self.references_list.InsertItem(self.references_list.GetItemCount(), "—")
            self.references_list.SetItem(row, 3, "No known references")
            return
        for direction, reference in self._reference_rows:
            row = self.references_list.InsertItem(
                self.references_list.GetItemCount(),
                direction,
            )
            self.references_list.SetItem(row, 1, reference_kind(reference))
            self.references_list.SetItem(row, 2, reference.path)
            self.references_list.SetItem(row, 3, reference_info(reference))

    def _show_references(self, visible: bool) -> None:
        if visible:
            if not self.reference_splitter.IsSplit():
                self.reference_splitter.SplitHorizontally(
                    self.editor_panel,
                    self.references_panel,
                    self.FromDIP(170),
                )
            self.references_panel.Show()
        elif self.reference_splitter.IsSplit():
            self.reference_splitter.Unsplit(self.references_panel)
        self.Layout()

    def _on_references_size(self, event: wx.SizeEvent) -> None:
        event.Skip()
        width = self.references_list.GetClientSize().width
        fixed = sum(self.references_list.GetColumnWidth(i) for i in range(3))
        scrollbar = self.FromDIP(18)
        self.references_list.SetColumnWidth(
            3,
            max(self.FromDIP(220), width - fixed - scrollbar),
        )

    def _on_reference_activated(self, event: wx.ListEvent) -> None:
        index = event.GetIndex()
        if not 0 <= index < len(self._reference_rows) or self._on_navigate is None:
            return
        self._on_navigate(self._reference_rows[index][1].path)

    def _on_reference_context(self, event: wx.ContextMenuEvent) -> None:
        if not self._reference_rows:
            return
        index = self.references_list.GetFirstSelected()
        if index < 0 or index >= len(self._reference_rows):
            return
        direction, reference = self._reference_rows[index]
        menu = wx.Menu()
        copy_path = menu.Append(wx.ID_ANY, "Copy path")
        copy_description = menu.Append(wx.ID_ANY, "Copy info")
        open_reference = menu.Append(wx.ID_ANY, "Open reference")
        self.Bind(wx.EVT_MENU, lambda _event: self._copy_text(reference.path), copy_path)
        self.Bind(wx.EVT_MENU, lambda _event: self._copy_text(reference_info(reference)), copy_description)
        self.Bind(
            wx.EVT_MENU,
            lambda _event: self._on_navigate(reference.path) if self._on_navigate else None,
            open_reference,
        )
        self.PopupMenu(menu)
        menu.Destroy()

    @staticmethod
    def _copy_text(value: str) -> None:
        if not wx.TheClipboard.Open():
            return
        try:
            wx.TheClipboard.SetData(wx.TextDataObject(value))
        finally:
            wx.TheClipboard.Close()
