"""Diagnostics and byte-preservation records.

These types let every layer report what it could not interpret, instead
of repairing or discarding input silently (effdir-editor-spec.md,
"Parsing contract").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

from .cursor import SourceSpan


@dataclass(frozen=True)
class Diagnostic:
    severity: str  # "error" | "warning" | "info"
    code: str
    message: str
    path: Optional[str] = None
    source_span: Optional[SourceSpan] = None


@dataclass(frozen=True)
class RawValue:
    path: str
    wire_type: str
    raw_bytes: bytes
    value: Optional[Any] = None
    source_span: Optional[SourceSpan] = None


@dataclass
class RecordPreservation:
    """Per-record leftovers: bytes and members a record reader could not
    place into a named field, kept so a lossless write can reproduce them."""

    original_bytes: Optional[bytes] = None
    unknown_members: List[RawValue] = field(default_factory=list)
    original_order: Optional[List[str]] = None


@dataclass
class PreservationData:
    """Resource-level leftovers: gated/unsupported records, trailing
    bytes, and every diagnostic raised while decoding."""

    original_payload: Optional[bytes] = None
    unknown_top_level: List[RawValue] = field(default_factory=list)
    version_gated_records: List[RawValue] = field(default_factory=list)
    trailing_bytes: bytes = b""
    diagnostics: List[Diagnostic] = field(default_factory=list)
