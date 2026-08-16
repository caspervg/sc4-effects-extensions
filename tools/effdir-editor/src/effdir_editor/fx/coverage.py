"""Coverage tracking for the EFFDIR -> fx emitter.

The emitter is a *best-effort, one-way* decompiler (see
docs/reference/binary/effdir.md and the repository README's "recovered"
framing): some binary fields have no confirmed fx spelling, some are
genuinely opaque, and some collapse several fx spellings into one wire
field so the original spelling cannot be recovered. Coverage notes make
that honest instead of silently guessing -- the same `Confirmed` /
`Partial` / `Inferred` spirit the documentation pages use.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Any, List

Severity = str  # "info" | "unsupported" | "ambiguous"


@dataclass(frozen=True)
class CoverageNote:
    path: str
    severity: Severity
    message: str

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return f"[{self.severity}] {self.path}: {self.message}"


@dataclass
class Coverage:
    notes: List[CoverageNote] = field(default_factory=list)
    fields_considered: int = 0
    fields_emitted: int = 0

    def note(self, path: str, severity: Severity, message: str) -> None:
        self.notes.append(CoverageNote(path=path, severity=severity, message=message))

    def emitted(self, count: int = 1) -> None:
        self.fields_considered += count
        self.fields_emitted += count

    def skipped(self, path: str, message: str, *, severity: Severity = "unsupported", count: int = 1) -> None:
        self.fields_considered += count
        self.note(path, severity, message)

    def merge(self, other: "Coverage") -> None:
        self.notes.extend(other.notes)
        self.fields_considered += other.fields_considered
        self.fields_emitted += other.fields_emitted

    @property
    def ratio(self) -> float:
        if self.fields_considered == 0:
            return 1.0
        return self.fields_emitted / self.fields_considered

    def notes_by_severity(self, severity: Severity) -> List[CoverageNote]:
        return [n for n in self.notes if n.severity == severity]

    def summary_lines(self) -> List[str]:
        unsupported = len(self.notes_by_severity("unsupported"))
        ambiguous = len(self.notes_by_severity("ambiguous"))
        info = len(self.notes_by_severity("info"))
        lines = [
            f"{self.fields_emitted}/{self.fields_considered} tracked fields emitted "
            f"({self.ratio * 100:.1f}%)" if self.fields_considered else "no fields tracked",
        ]
        if unsupported:
            lines.append(f"{unsupported} unsupported (no confirmed fx spelling)")
        if ambiguous:
            lines.append(f"{ambiguous} ambiguous (ground truth cannot be recovered)")
        if info:
            lines.append(f"{info} informational notes (e.g. synthesized names)")
        return lines


@dataclass(frozen=True)
class FxEmitResult:
    text: str
    coverage: Coverage

    def summary(self) -> str:
        return "\n".join(self.coverage.summary_lines())


_MAX_SCAN_DEPTH = 12


def note_non_finite_floats(record: Any, path: str, coverage: Coverage, *, _depth: int = 0) -> None:
    """Walk a decoded record and report every NaN/infinity it holds.

    There is no fx literal for a non-finite float, and `fmt_num` degrades
    them to ``0`` so one bad value cannot abort an export -- which would
    silently misrepresent the data if it went unreported. Scanning the
    record generically (rather than checking fields one at a time in each
    emitter) means a field added to the model later is covered without
    touching this code, and matches the "non-finite floats" diagnostic
    class the editor's own validation.py already recognizes.
    """

    if _depth > _MAX_SCAN_DEPTH:
        return

    if isinstance(record, bool) or record is None:
        return
    if isinstance(record, float):
        if not math.isfinite(record):
            coverage.note(path, "unsupported", f"non-finite float ({record!r}) has no fx literal; emitted as 0")
        return
    if isinstance(record, (str, bytes, int)):
        return

    if hasattr(record, "wire_type"):  # wire.Raw[T]: only .value can be a float
        note_non_finite_floats(record.value, path, coverage, _depth=_depth + 1)
        return
    if hasattr(record, "raw_bytes") and hasattr(record, "decoded"):  # wire.WireString
        return

    items = getattr(record, "items", None)
    if isinstance(items, list):  # wire.WireVector[T]
        for i, item in enumerate(items):
            note_non_finite_floats(item, f"{path}[{i}]", coverage, _depth=_depth + 1)
        return

    if dataclasses.is_dataclass(record):
        for f in dataclasses.fields(record):
            if f.name == "preservation":
                continue
            note_non_finite_floats(getattr(record, f.name), f"{path}.{f.name}", coverage, _depth=_depth + 1)
