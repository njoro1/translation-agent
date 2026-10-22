"""Qt item models behind the Review and Quality screens.

Three models live here:

* :class:`CueResultModel` — the editable cue list (one row per subtitle cue).
* :class:`CueFilterProxyModel` — All / OK / Warnings / Failed / Errors
  filtering, a case-insensitive search and a cue-number range, over the cue
  model.
* :class:`QualityIssuesModel` — a flat list of quality issues, one row per
  *issue* (a single cue can carry several), with an All / Errors / Warnings
  filter.

The cue model is the single source of truth for the Review screen: the QML
table never keeps its own copy, so an edit made in the inspector is the same
edit the Quality screen re-checks.
"""
from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    QSortFilterProxyModel,
    Qt,
    Signal,
    Slot,
)

__all__ = [
    "CueResultModel",
    "CueFilterProxyModel",
    "QualityIssuesModel",
]

#: The marker the pipeline writes when a cue could not be translated.
UNTRANSLATED_MARKER = "[untranslated]"

# --- Review filter modes ----------------------------------------------------
FILTER_ALL = "all"
FILTER_OK = "ok"
FILTER_WARNINGS = "warnings"
FILTER_FAILED = "failed"
FILTER_ERRORS = "errors"

#: Statuses that mean "this cue was not translated".
_FAILED_STATUSES = ("untranslated", "empty")

_STATUS_ORDER = {
    "untranslated": 0,
    "empty": 1,
    "warning": 2,
    "error": 3,
    "ok": 4,
}

_SEVERITY_ORDER = {"error": 0, "warning": 1}


def _format_ms(ms: float) -> str:
    """``mm:ss.mmm`` (or ``h:mm:ss.mmm``) from milliseconds."""
    total = int(max(0.0, float(ms or 0.0)))
    hours, rem = divmod(total, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def _derive_status(text: str, status: str, tags) -> str:
    """The status a cue is shown under, derived from its text and its tags.

    The pipeline writes ``ok`` / ``warning`` / ``untranslated``; the Review
    screen also needs ``empty`` (a cue with no text at all) and it needs a
    flagged-but-translated cue to read as a problem rather than as clean. A
    cue carrying any quality tag is therefore a ``warning`` unless the
    pipeline said otherwise, and the text always wins over a stale status: a
    cue the user just fixed stops being a failure.
    """
    stripped = (text or "").strip()
    if not stripped:
        return "empty"
    if stripped == UNTRANSLATED_MARKER:
        return "untranslated"
    if status in ("error", "warning"):
        return status
    if tags:
        return "warning"
    return "ok"


def _severity_of(tag: str) -> str:
    """``error`` / ``warning`` for a quality tag.

    Mirrors ``src.subtitle_quality.CueIssue.has_errors``: a tag ending in
    ``_error`` (or the bare ``empty_text``) is an error, everything else is a
    warning.
    """
    if tag == "empty_text" or tag.endswith("_error"):
        return "error"
    return "warning"


#: A human phrase for every quality tag the checker can produce. The raw tag
#: stays available next to it, so the phrase never has to be parsed back.
_FRIENDLY_MESSAGES = {
    "empty_text": "Cue has no translated text",
    "untranslated_marker_error": "Carries the [untranslated] marker",
    "asr_tag_leakage_error": "ASR tag leaked into output",
    "fansub_markup_error": "Fansub markup leaked into output",
    "cjk_residue_error": "CJK residue in English output",
    "cjk_residue_warning": "CJK residue in English output",
    "duplicate_translation_warning": "Duplicate of previous translation",
    "overlap_warning": "Overlaps the previous cue",
    "cps_error": "Reading speed is too fast to read",
    "cps_warning": "Reading speed is too fast to read comfortably",
    "chars_error": "Line is too long to read",
    "chars_warning": "Line is too long to read comfortably",
    "too_short_error": "Cue is on screen too briefly",
    "too_short_warning": "Cue is on screen too briefly",
    "too_long_error": "Cue stays on screen too long",
    "too_long_warning": "Cue stays on screen too long",
    "lines_error": "Too many lines for one cue",
    "lines_warning": "Too many lines for one cue",
}


def _friendly_message(tag: str) -> str:
    """A human phrase for a quality tag.

    An unknown tag falls back to the tag with its underscores turned into
    spaces, so a newly added check is still readable rather than blank.
    """
    return _FRIENDLY_MESSAGES.get(tag, tag.replace("_", " "))


class CueResultModel(QAbstractListModel):
    """The editable list of cues behind the Review table.

    The model owns the cue list; QML only reads roles and writes the
    translation text back through :meth:`setData`. Every edit is compared
    against a snapshot taken at load time, which is what ``cueEdited`` and
    ``edited_count()`` report.
    """

    IndexRole = Qt.UserRole + 1
    StartRole = Qt.UserRole + 2
    EndRole = Qt.UserRole + 3
    SourceRole = Qt.UserRole + 4
    TextRole = Qt.UserRole + 5
    StatusRole = Qt.UserRole + 6
    TagsRole = Qt.UserRole + 7
    EditedRole = Qt.UserRole + 8

    countChanged = Signal()
    editedCountChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cues: list[dict] = []
        self._original: list[str] = []
        self._provided: list[str] = []

    # --- Population ---------------------------------------------------------

    def load(self, cues, tags_by_index=None) -> None:
        """Replace the cue list.

        ``tags_by_index`` maps a *row* (0-based) to the quality tags that row
        carries. The report's ``cue_index`` is a row, not a cue number, so the
        two agree.
        """
        mapping = tags_by_index or {}
        self.beginResetModel()
        try:
            self._cues = []
            self._original = []
            self._provided = []
            for row, raw in enumerate(cues or []):
                cue = dict(raw)
                cue.setdefault("index", row + 1)
                tags = list(mapping.get(row, cue.get("tags") or []))
                cue["tags"] = tags
                provided = str(cue.get("status", "ok") or "ok")
                cue["status"] = _derive_status(cue.get("text", ""), provided, tags)
                self._cues.append(cue)
                self._original.append(str(cue.get("text", "") or ""))
                self._provided.append(provided)
        finally:
            self.endResetModel()
        self.countChanged.emit()
        self.editedCountChanged.emit()

    @Slot()
    def clear(self) -> None:
        self.beginResetModel()
        try:
            self._cues = []
            self._original = []
            self._provided = []
        finally:
            self.endResetModel()
        self.countChanged.emit()
        self.editedCountChanged.emit()

    def set_tags(self, tags_by_index) -> None:
        """Replace the per-row quality tags.

        The report is the authority: a row that no longer appears in it has no
        tags, so a fixed cue stops being counted as a problem.
        """
        mapping = tags_by_index or {}
        changed = False
        for row, cue in enumerate(self._cues):
            tags = list(mapping.get(row, []))
            if cue.get("tags") != tags:
                cue["tags"] = tags
                changed = True
            status = _derive_status(cue.get("text", ""), self._provided[row], tags)
            if cue.get("status") != status:
                cue["status"] = status
                changed = True
        if not changed or not self._cues:
            return
        top = self.index(0, 0)
        bottom = self.index(len(self._cues) - 1, 0)
        self.dataChanged.emit(top, bottom, [self.TagsRole, self.StatusRole])

    # --- Qt model interface -------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._cues)

    def roleNames(self) -> dict:
        return {
            self.IndexRole: b"cueIndex",
            self.StartRole: b"startText",
            self.EndRole: b"endText",
            self.SourceRole: b"sourceText",
            self.TextRole: b"translationText",
            self.StatusRole: b"statusText",
            self.TagsRole: b"cueTags",
            self.EditedRole: b"cueEdited",
        }

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        if not (0 <= row < len(self._cues)):
            return None
        cue = self._cues[row]
        if role == self.IndexRole:
            return int(cue.get("index", row + 1))
        if role == self.StartRole:
            return _format_ms(cue.get("start_ms", 0))
        if role == self.EndRole:
            return _format_ms(cue.get("end_ms", 0))
        if role == self.SourceRole:
            return str(cue.get("source", "") or "")
        if role in (self.TextRole, Qt.EditRole, Qt.DisplayRole):
            return str(cue.get("text", "") or "")
        if role == self.StatusRole:
            return str(cue.get("status", "ok") or "ok")
        if role == self.TagsRole:
            return list(cue.get("tags") or [])
        if role == self.EditedRole:
            return self._is_edited(row)
        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False
        row = index.row()
        if not (0 <= row < len(self._cues)):
            return False
        if role not in (self.TextRole, Qt.EditRole):
            return False
        text = "" if value is None else str(value)
        cue = self._cues[row]
        if text == str(cue.get("text", "") or ""):
            return False
        cue["text"] = text
        cue["status"] = _derive_status(
            text, self._provided[row], cue.get("tags") or []
        )
        idx = self.index(row, 0)
        self.dataChanged.emit(
            idx, idx, [self.TextRole, self.StatusRole, self.EditedRole]
        )
        self.editedCountChanged.emit()
        return True

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    # --- Editing helpers ----------------------------------------------------

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._cues)

    @Slot(result=int)
    def edited_count(self) -> int:
        """How many cues differ from the text the run produced."""
        return sum(1 for row in range(len(self._cues)) if self._is_edited(row))

    def _is_edited(self, row: int) -> bool:
        if not (0 <= row < len(self._cues)):
            return False
        return str(self._cues[row].get("text", "") or "") != self._original[row]

    @Slot(int)
    def revert_cue(self, row: int) -> None:
        if not (0 <= row < len(self._cues)):
            return
        cue = self._cues[row]
        original = self._original[row]
        if str(cue.get("text", "") or "") == original:
            return
        cue["text"] = original
        cue["status"] = _derive_status(
            original, self._provided[row], cue.get("tags") or []
        )
        idx = self.index(row, 0)
        self.dataChanged.emit(
            idx, idx, [self.TextRole, self.StatusRole, self.EditedRole]
        )
        self.editedCountChanged.emit()

    @Slot()
    def revert_all(self) -> None:
        changed = False
        for row, cue in enumerate(self._cues):
            original = self._original[row]
            if str(cue.get("text", "") or "") == original:
                continue
            cue["text"] = original
            cue["status"] = _derive_status(
                original, self._provided[row], cue.get("tags") or []
            )
            changed = True
        if not changed:
            return
        top = self.index(0, 0)
        bottom = self.index(len(self._cues) - 1, 0)
        self.dataChanged.emit(
            top, bottom, [self.TextRole, self.StatusRole, self.EditedRole]
        )
        self.editedCountChanged.emit()

    def get_cue(self, row: int) -> dict:
        """A copy of one cue — safe to hand out and mutate."""
        cue = self.peek_cue(row)
        return dict(cue) if cue is not None else {}

    def peek_cue(self, row: int):
        """One cue, by reference — cheap enough to call in a loop."""
        if not (0 <= row < len(self._cues)):
            return None
        return self._cues[row]

    @Slot(int, float, float)
    def set_times(self, row: int, start_ms: float, end_ms: float) -> None:
        if not (0 <= row < len(self._cues)):
            return
        cue = self._cues[row]
        cue["start_ms"] = float(start_ms)
        cue["end_ms"] = float(end_ms)
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx, [self.StartRole, self.EndRole])


class CueFilterProxyModel(QSortFilterProxyModel):
    """Filtering, search and cue-range selection over :class:`CueResultModel`.

    The proxy is the only thing the Review table talks to, so the filter mode,
    the search text and the selected cue range compose instead of fighting
    over one axis.
    """

    filterModeChanged = Signal()
    searchTextChanged = Signal()
    countChanged = Signal()
    cueRangeChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._filter_mode = FILTER_ALL
        self._search_text = ""
        self._range_first: int | None = None
        self._range_last: int | None = None
        self.setDynamicSortFilter(True)

    # --- Filter mode --------------------------------------------------------

    @Property(str, notify=filterModeChanged)
    def filterMode(self) -> str:
        return self._filter_mode

    @filterMode.setter
    def filterMode(self, value: str) -> None:
        mode = str(value or FILTER_ALL)
        if mode == self._filter_mode:
            return
        self._filter_mode = mode
        self.invalidateRowsFilter()
        self.filterModeChanged.emit()
        self.countChanged.emit()

    # --- Search -------------------------------------------------------------

    @Property(str, notify=searchTextChanged)
    def searchText(self) -> str:
        return self._search_text

    @searchText.setter
    def searchText(self, value: str) -> None:
        text = str(value or "")
        if text == self._search_text:
            return
        self._search_text = text
        self.invalidateRowsFilter()
        self.searchTextChanged.emit()
        self.countChanged.emit()

    # --- Cue range ----------------------------------------------------------

    @Property(bool, notify=cueRangeChanged)
    def hasCueRange(self) -> bool:
        return self._range_first is not None and self._range_last is not None

    @Property(str, notify=cueRangeChanged)
    def cueRangeLabel(self) -> str:
        if not self.hasCueRange:
            return ""
        return f"cues {self._range_first}\u2013{self._range_last}"

    @Slot(int, int)
    def setCueRange(self, first: int, last: int) -> None:
        low = max(1, int(first))
        high = max(low, int(last))
        if self._range_first == low and self._range_last == high:
            return
        self._range_first = low
        self._range_last = high
        self.invalidateRowsFilter()
        self.cueRangeChanged.emit()
        self.countChanged.emit()

    @Slot()
    def clearCueRange(self) -> None:
        if self._range_first is None and self._range_last is None:
            return
        self._range_first = None
        self._range_last = None
        self.invalidateRowsFilter()
        self.cueRangeChanged.emit()
        self.countChanged.emit()

    # --- Row access ---------------------------------------------------------

    @Slot(int, result="QVariantMap")
    def get(self, row: int) -> dict:
        """The cue behind a *visible* row, for the cue inspector."""
        index = self.index(row, 0)
        if not index.isValid():
            return {}
        source = self.mapToSource(index)
        if not source.isValid():
            return {}
        model = self.sourceModel()
        if not isinstance(model, CueResultModel):
            return {}
        return model.get_cue(source.row())

    # --- Filtering ----------------------------------------------------------

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if not isinstance(model, CueResultModel):
            return True
        cue = model.peek_cue(source_row)
        if cue is None:
            return False

        if self._range_first is not None and self._range_last is not None:
            index = int(cue.get("index", source_row + 1))
            if not (self._range_first <= index <= self._range_last):
                return False

        status = str(cue.get("status", "ok") or "ok")
        tags = list(cue.get("tags") or [])
        mode = self._filter_mode
        if mode == FILTER_FAILED:
            if status not in _FAILED_STATUSES:
                return False
        elif mode == FILTER_OK:
            if status != "ok":
                return False
        elif mode == FILTER_WARNINGS:
            if not any(str(tag).endswith("_warning") for tag in tags):
                return False
        elif mode == FILTER_ERRORS:
            if not self._is_error(status, tags):
                return False

        needle = self._search_text.strip().casefold()
        if needle:
            haystack = f"{cue.get('source', '')}\n{cue.get('text', '')}".casefold()
            if needle not in haystack:
                return False
        return True

    @staticmethod
    def _is_error(status: str, tags) -> bool:
        if status in _FAILED_STATUSES:
            return True
        for tag in tags:
            tag = str(tag)
            if tag == "empty_text" or tag.endswith("_error"):
                return True
        return False


class QualityIssuesModel(QAbstractListModel):
    """A flat list of quality issues — one row per issue, not per cue.

    A single cue can carry several issues (a blank cue is both
    ``empty_text`` and ``cps_error``), so the table counts *rows* while the
    Review screen counts *cues*. Both are right for their own screen; the
    units are kept apart deliberately.
    """

    CueRole = Qt.UserRole + 1
    IssueTypeRole = Qt.UserRole + 2
    SeverityRole = Qt.UserRole + 3
    MessageRole = Qt.UserRole + 4
    FriendlyTypeRole = Qt.UserRole + 5
    RawTypeRole = Qt.UserRole + 6

    countChanged = Signal()
    filterModeChanged = Signal()
    focusCueChanged = Signal()
    severitySortChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._all_issues: list[dict] = []
        self._issues: list[dict] = []
        self._filter_mode = "all"
        self._severity_sort = True
        self._focus_cue = 0

    # --- Population ---------------------------------------------------------

    @Slot(dict)
    def load_from_report(self, report) -> None:
        """Rebuild the issue rows from a quality report."""
        rows: list[dict] = []
        for entry in (report or {}).get("issues", []) or []:
            cue_index = int(entry.get("cue_index", 0) or 0)
            for tag in entry.get("issues", []) or []:
                tag = str(tag)
                rows.append({
                    "cue": cue_index + 1,
                    "cue_index": cue_index,
                    "tag": tag,
                    "severity": _severity_of(tag),
                    "message": _friendly_message(tag),
                })
        self._all_issues = rows
        self._apply_filter()

    @Slot()
    def clear(self) -> None:
        self._all_issues = []
        self._focus_cue = 0
        self._apply_filter()
        self.focusCueChanged.emit()

    def _apply_filter(self) -> None:
        self.beginResetModel()
        try:
            mode = self._filter_mode
            if mode == "errors":
                rows = [r for r in self._all_issues if r["severity"] == "error"]
            elif mode == "warnings":
                rows = [r for r in self._all_issues if r["severity"] == "warning"]
            else:
                rows = list(self._all_issues)
            self._issues = self._sort(rows)
        finally:
            self.endResetModel()
        self.countChanged.emit()

    def _sort(self, rows: list[dict]) -> list[dict]:
        # The sort is stable on purpose: two issues on the same cue keep the
        # order the report gave them, so the table reads the way the checker
        # found them rather than in an arbitrary order.
        if self._severity_sort:
            return sorted(
                rows,
                key=lambda r: (
                    _SEVERITY_ORDER.get(r["severity"], 1),
                    r["cue"],
                ),
            )
        return sorted(rows, key=lambda r: r["cue"])

    # --- Qt model interface -------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._issues)

    def roleNames(self) -> dict:
        return {
            self.CueRole: b"cueNumber",
            self.IssueTypeRole: b"issueType",
            self.SeverityRole: b"severity",
            self.MessageRole: b"message",
            self.FriendlyTypeRole: b"friendlyType",
            self.RawTypeRole: b"rawType",
        }

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        if not (0 <= row < len(self._issues)):
            return None
        issue = self._issues[row]
        if role == self.CueRole:
            return int(issue["cue"])
        if role in (self.IssueTypeRole, self.RawTypeRole):
            return str(issue["tag"])
        if role == self.SeverityRole:
            return str(issue["severity"])
        if role in (self.MessageRole, self.FriendlyTypeRole, Qt.DisplayRole):
            return str(issue["message"])
        return None

    # --- Filter, sort, focus ------------------------------------------------

    @Property(str, notify=filterModeChanged)
    def filterMode(self) -> str:
        return self._filter_mode

    @filterMode.setter
    def filterMode(self, value: str) -> None:
        mode = str(value or "all")
        if mode == self._filter_mode:
            return
        self._filter_mode = mode
        self._apply_filter()
        self.filterModeChanged.emit()

    @Property(bool, notify=severitySortChanged)
    def severitySort(self) -> bool:
        return self._severity_sort

    @Slot(bool)
    def set_severity_sort(self, enabled: bool) -> None:
        """Sort errors first (or by cue number) without losing a row."""
        value = bool(enabled)
        if value == self._severity_sort:
            return
        self._severity_sort = value
        self._apply_filter()
        self.severitySortChanged.emit()

    @Property(int, notify=focusCueChanged)
    def focusCue(self) -> int:
        return self._focus_cue

    @Slot(int)
    def focus_cue(self, cue_number: int) -> None:
        """Ask the table to scroll to a cue's first issue row.

        The filter is widened first: a jump that lands on a row the current
        filter excludes silently does nothing.
        """
        number = int(cue_number or 0)
        if number <= 0:
            return
        if self._filter_mode != "all":
            self._filter_mode = "all"
            self._apply_filter()
            self.filterModeChanged.emit()
        self._focus_cue = number
        self.focusCueChanged.emit()

    @Slot(int, result=int)
    def row_for_cue(self, cue_number: int) -> int:
        """The visible row of a cue's first issue, or -1."""
        number = int(cue_number or 0)
        for row, issue in enumerate(self._issues):
            if issue["cue"] == number:
                return row
        return -1

    # --- Aggregates ---------------------------------------------------------

    @Property("QVariantMap", notify=countChanged)
    def counts(self) -> dict:
        """Issue-row counts, derived from *all* issues, not the filtered ones.

        Counting the filtered list is the obvious mistake: selecting "Errors"
        would make the Warnings chip read 0.
        """
        errors = sum(1 for r in self._all_issues if r["severity"] == "error")
        warnings = sum(1 for r in self._all_issues if r["severity"] == "warning")
        return {
            "all": errors + warnings,
            "errors": errors,
            "warnings": warnings,
        }

    @Slot(str, result="QVariantList")
    def breakdown(self, severity: str) -> list:
        """The rows of one severity grouped by kind — the chip's click-through.

        Same rows the table renders, so the chip and the table cannot
        disagree.
        """
        wanted = str(severity or "").casefold()
        grouped: dict[str, int] = {}
        for issue in self._all_issues:
            if issue["severity"] != wanted:
                continue
            key = issue["message"]
            grouped[key] = grouped.get(key, 0) + 1
        return [
            {"k": key, "v": count}
            for key, count in sorted(grouped.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
