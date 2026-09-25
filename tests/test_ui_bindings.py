"""Binding hygiene: every bound editor must keep mirroring the store.

This is the regression suite for the review's root cause RC-1. The bug was
never "there is no store" — `AppBridge` has always been the store. The bug was
that editors declared

    currentIndex: { …appBridge.someValue… }

on a `ComboBox`. `ComboBox` assigns `currentIndex` internally when the user
activates an item, and that internal assignment *destroys the declarative
binding*. So from the second interaction onward the widget stopped mirroring
the store, and any second editor for the same concept silently disagreed.

Every test here therefore does the same three things, in order:

1. write a probe value through the store (baseline: the mirror works at all),
2. simulate the user having interacted — assign `currentIndex` / `editText`
   directly, which is exactly what the control does internally,
3. change the store again and assert the widget followed.

Step 2 is what makes this a regression test rather than a tautology. Without
it, a plain `currentIndex: { … }` binding would pass.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QObject

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"
COMPONENTS_DIR = QML_DIR / "components"
PAGES_DIR = QML_DIR / "pages"

# Every store attribute these tests mutate. Snapshotted and restored so the
# session-scoped `qml_main` bridge is left exactly as it was found.
STORE_ATTRS = (
    "outputFormat",
    "contextMode",
    "translationMemoryMode",
    "sourceLang",
    "asrLanguage",
    "asrPreprocess",
    "themeName",
    "comfortable",
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def by_name(root: QObject, name: str) -> QObject:
    """The one QML object carrying `objectName == name`."""
    for obj in root.findChildren(QObject):
        if obj.objectName() == name:
            return obj
    raise AssertionError(
        f"no QML object named {name!r}. It was renamed or deleted — update the "
        f"editor map in AGENT_DOCUMENTATION.md and this table together."
    )


def option_values(widget: QObject) -> list[str]:
    """The `valueRole` (or the literal) of every entry in a ComboBox's model."""
    model = widget.property("model") or []
    role = widget.property("valueRole") or ""
    out: list[str] = []
    for item in model:
        if isinstance(item, dict):
            out.append(str(item.get(role, item.get("id", item.get("label", "")))))
        else:
            out.append(str(item))
    return out


def index_of(values: list[str], value: str) -> int:
    return values.index(value) if value in values else -1


def store_index(values: list[str], store, attr: str) -> int:
    return index_of(values, getattr(store, attr))


@pytest.fixture()
def store(qml_main):
    """The live `AppBridge`, restored to its entry state on teardown."""
    bridge = qml_main.bridge
    saved = {attr: getattr(bridge, attr) for attr in STORE_ATTRS}
    yield bridge
    for attr, value in saved.items():
        setattr(bridge, attr, value)


# --------------------------------------------------------------------------- #
# RC-1: dropdowns survive a user pick
# --------------------------------------------------------------------------- #

DROPDOWNS = (
    ("bound.run.outputFormat", "outputFormat"),
    ("bound.run.contextMode", "contextMode"),
    ("bound.run.translationMemory", "translationMemoryMode"),
    ("bound.settings.contextMode", "contextMode"),
    ("bound.settings.translationMemory", "translationMemoryMode"),
    ("bound.settings.ffmpegPreprocess", "asrPreprocess"),
)


@pytest.mark.parametrize("name, attr", DROPDOWNS)
def test_dropdown_mirrors_the_store_after_the_user_has_picked(
    qml_main, store, name, attr
):
    widget = by_name(qml_main.root, name)
    values = option_values(widget)
    assert len(values) >= 2, f"{name} needs two options to exercise a pick"
    assert values[0] != values[1], f"{name} has duplicate option values"

    # Baseline: the store write reaches the widget.
    setattr(store, attr, values[0])
    assert store_index(values, store, attr) == 0, (
        f"{name}: the store rejected the probe value {values[0]!r} "
        f"(it now reads {getattr(store, attr)!r}); pick a different probe"
    )
    assert widget.property("currentIndex") == 0

    # The mutation that used to break the binding, applied by hand.
    widget.setProperty("currentIndex", 1)

    # An external change must still win.
    setattr(store, attr, values[1])
    assert widget.property("currentIndex") == 1, (
        f"{name} stopped mirroring appBridge.{attr} after being interacted "
        f"with — this is RC-1. Do not go back to `currentIndex: {{ … }}`; "
        f"re-apply the index imperatively on notify."
    )


# --------------------------------------------------------------------------- #
# RC-1: editable fields survive typing
# --------------------------------------------------------------------------- #

def test_spoken_language_field_mirrors_the_store_after_typing(qml_main, store):
    widget = by_name(qml_main.root, "bound.settings.spokenLanguage")

    store.asrLanguage = "ja"
    assert widget.property("editText") == "ja"

    # Typing destroys a binding over `editText`; do it by hand.
    widget.setProperty("editText", "ja, being typed")

    store.asrLanguage = "ko"
    assert widget.property("editText") == "ko", (
        "the spoken-language field stopped mirroring appBridge.asrLanguage "
        "after the user typed in it — this is the `editText:` half of RC-1."
    )


def test_run_language_field_tracks_whichever_store_attribute_is_live(
    qml_main, store
):
    """One control, two backing attributes, chosen by the source axis.

    The review asked for the language control to be present in *every* mode
    (§6.5). It reads `sourceLang` for YouTube and `asrLanguage` for a local
    file, so both directions are exercised here.
    """
    widget = by_name(qml_main.root, "bound.run.language")

    assert store.setSourceEngine("youtube", "cloud") == ""
    store.sourceLang = "ja"
    assert widget.property("editText") == "ja"

    assert store.setSourceEngine("localfile", "cloud") == ""
    store.asrLanguage = "ko"
    assert widget.property("editText") == "ko", (
        "the Run language field did not follow the local-file attribute after "
        "the source axis changed"
    )


# --------------------------------------------------------------------------- #
# Segmented controls: `current` must never be assigned by the control
# --------------------------------------------------------------------------- #

def test_theme_toggle_and_its_settings_mirror_agree(qml_main, store):
    """Two widgets, one concept: this is the exact report the review filed."""
    chrome = by_name(qml_main.root, "bound.chrome.theme")
    settings = by_name(qml_main.root, "bound.settings.theme")

    store.themeName = "light"
    assert chrome.property("current") == "light"
    assert settings.property("current") == "light"

    store.themeName = "dark"
    assert chrome.property("current") == "dark"
    assert settings.property("current") == "dark", (
        "the top-bar theme toggle and the Settings theme control disagree — "
        "they must both read appBridge.themeName declaratively and never "
        "assign to their own `current`."
    )


def test_density_toggle_mirrors_the_boolean_store(qml_main, store):
    widget = by_name(qml_main.root, "bound.settings.density")

    store.comfortable = True
    assert widget.property("current") == "comfortable"

    store.comfortable = False
    assert widget.property("current") == "compact"


def test_source_and_engine_axes_stay_independent(qml_main, store):
    source = by_name(qml_main.root, "bound.run.source")
    engine = by_name(qml_main.root, "bound.run.engine")

    assert store.setSourceEngine("youtube", "cloud") == ""
    assert source.property("current") == "youtube"
    assert engine.property("current") == "cloud"

    assert store.setSourceEngine("localfile", "local") == ""
    assert source.property("current") == "localfile"
    assert engine.property("current") == "local"

    # The two axes are orthogonal: moving one must not move the other.
    assert store.setSourceEngine("localfile", "cloud") == ""
    assert source.property("current") == "localfile"
    assert engine.property("current") == "cloud"


# --------------------------------------------------------------------------- #
# The fourth matrix cell is honest (review §6.1)
# --------------------------------------------------------------------------- #

def test_youtube_plus_local_engine_is_refused_with_a_reason(store):
    problem = store.setSourceEngine("youtube", "local")
    assert problem != "", "the unsupported cell was accepted silently"
    assert "local" in problem.lower()


def test_engine_local_disabled_reason_tracks_the_source_axis(store):
    """The reason gates the *option*, so it follows the source, not the pair.

    Testing the current pair made the property unreachable: `pipelineMode` can
    only hold one of the three supported combinations, so `youtube + local` is
    never the current state and the explanation never rendered.
    """
    for source, expected in (("youtube", True), ("localfile", False)):
        for engine in ("cloud", "local"):
            if source == "youtube" and engine == "local":
                continue  # refused outright, tested above
            assert store.setSourceEngine(source, engine) == ""
            assert (store.engineLocalDisabledReason != "") is expected, (
                f"{source}+{engine}: the disabled reason is on the wrong side"
            )


# --------------------------------------------------------------------------- #
# Static guards — cheap, and they catch the next editor before it ships broken
# --------------------------------------------------------------------------- #

def _qml_sources() -> list[Path]:
    return [p for p in QML_DIR.rglob("*.qml") if "archive" not in p.parts]


def test_no_qml_file_binds_currentIndex_or_editText_to_the_store():
    """A declarative binding on `currentIndex` / `editText` is always a bug."""
    pattern = re.compile(r"^\s*(currentIndex|editText)\s*:\s*.*appBridge")
    offenders: list[str] = []
    for path in _qml_sources():
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if pattern.match(line):
                offenders.append(f"{path.relative_to(QML_DIR.parent.parent)}:{lineno}")
    assert not offenders, (
        "these bindings are destroyed by the control's own internal "
        "assignment (RC-1). Wrap the control in BoundComboBox / BoundField:\n  "
        + "\n  ".join(offenders)
    )


def test_every_bound_editor_is_covered_by_this_suite():
    """A new editor without a test is how the last round of drift got in."""
    declared = set()
    for path in _qml_sources():
        for match in re.finditer(r'objectName:\s*"(bound\.[^"]+)"', path.read_text(encoding="utf-8")):
            declared.add(match.group(1))

    covered = {name for name, _ in DROPDOWNS}
    covered |= {
        "bound.settings.spokenLanguage",
        "bound.run.language",
        "bound.chrome.theme",
        "bound.settings.theme",
        "bound.settings.density",
        "bound.run.source",
        "bound.run.engine",
    }

    assert declared, "no `bound.*` object names found — the naming convention was dropped"
    missing = sorted(declared - covered)
    assert not missing, (
        "these bound editors have no binding-hygiene test; add them to the "
        "table above:\n  " + "\n  ".join(missing)
    )
