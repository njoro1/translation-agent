"""Phase 6 gate — the command palette's four namespaces.

`§4.2` asked for Navigate / Actions / Toggles / Jump-to-setting. The failure mode
this file guards against is not cosmetic: a palette entry whose `action` is not in
`_run`'s switch, or whose jump target does not exist, is a command that looks real
and does nothing when invoked. That is worse than a missing command, and it is
invisible to a QML smoke test because the file still loads.

Everything here is derived from the two QML files, so the assertions cannot drift
from the source they describe.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

QML_DIR = Path(__file__).resolve().parent.parent / "ui" / "qml"

NAMESPACES = ("Navigate", "Actions", "Toggles", "Settings")

# The plan's §4.2 lists these eight Actions by name.
REQUIRED_ACTIONS = (
    "Start translation run",
    "Cancel current run",
    "Export quality report (JSON)",
    "Re-check quality",
    "Open the output file",
    "Choose glossary file…",
    "Purge the translation-memory cache…",
    "Download translation model",
)

TOGGLE_STORES = {
    "theme": "appBridge.themeName",
    "gate": "appBridge.strictQuality",
    "summary": "appBridge.contextSummary",
    "motion": "appBridge.reducedMotion",
}


def qml(rel: str) -> str:
    return (QML_DIR / rel).read_text(encoding="utf-8")


def _entries() -> list[dict]:
    """Parse `allCommands` into dicts, brace-matching so multi-line entries work."""
    source = qml("components/CommandPalette.qml")
    body = source.split("readonly property var allCommands: [", 1)[1]
    body = body.split("\n    ]", 1)[0]

    entries: list[dict] = []
    depth = 0
    buf = ""
    for ch in body:
        if ch == "{":
            depth += 1
            if depth == 1:
                buf = ""
                continue
        elif ch == "}":
            depth -= 1
            if depth == 0:
                entries.append(dict(re.findall(r'(\w+):\s*"([^"]*)"', buf)))
                continue
        if depth >= 1:
            buf += ch
    return entries


def _run_cases() -> set[str]:
    source = qml("components/CommandPalette.qml")
    body = source.split("function _run(entry) {", 1)[1].split("\n    }", 1)[0]
    return set(re.findall(r'case "([^"]+)":', body))


def _settings_sections() -> list[str]:
    source = qml("pages/SettingsPage.qml")
    body = source.split("readonly property var sections: [", 1)[1].split("]", 1)[0]
    return re.findall(r'id:\s*"([^"]+)"', body)


def _settings_object_names() -> set[str]:
    return set(re.findall(r'objectName:\s*"([^"]+)"', qml("pages/SettingsPage.qml")))


ENTRIES = _entries()


# --- Shape ------------------------------------------------------------------

def test_the_palette_has_entries():
    assert len(ENTRIES) > 20, "the palette lost most of its commands"


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.get("label", "?"))
def test_every_entry_declares_one_of_the_four_namespaces(entry):
    assert entry.get("ns") in NAMESPACES, entry


@pytest.mark.parametrize("namespace", NAMESPACES)
def test_each_namespace_is_populated(namespace):
    assert any(e.get("ns") == namespace for e in ENTRIES), (
        f"the {namespace} namespace is empty"
    )


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.get("label", "?"))
def test_every_entry_resolves_to_a_real_action(entry):
    """A command whose action is not in `_run`'s switch does nothing at all."""
    assert entry.get("action") in _run_cases(), (
        f"{entry.get('label')!r} dispatches {entry.get('action')!r}, which `_run` "
        f"does not handle"
    )


@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.get("label", "?"))
def test_every_entry_has_a_glyph_that_exists(entry):
    """A misspelled icon name renders nothing, silently."""
    paths = qml("components/Icon.qml").split("readonly property var _paths: ({", 1)[1]
    paths = paths.split("\n    })", 1)[0]
    known = set(re.findall(r"^\s*(\w+):", paths, re.MULTILINE))
    assert entry.get("icon") in known, (
        f"{entry.get('label')!r} uses icon {entry.get('icon')!r}, which Icon.qml "
        f"does not define"
    )


# --- Navigate ---------------------------------------------------------------

def test_navigate_covers_all_five_pages():
    labels = {e["label"] for e in ENTRIES if e.get("ns") == "Navigate"}
    for page in ("Run", "Review", "Quality", "Console", "Settings"):
        assert any(page in label for label in labels), f"no Navigate entry for {page}"


def test_navigate_deep_links_every_settings_category():
    """The rail's sections and the palette's deep links are one list, checked twice."""
    sections = _settings_sections()
    assert sections, "could not read SettingsPage.sections"
    linked = {
        e.get("section") for e in ENTRIES
        if e.get("ns") == "Navigate" and e.get("target") == ""
    }
    for section in sections:
        assert section in linked, (
            f"the {section!r} category has no palette deep link; typing its name "
            f"cannot reach it"
        )


# --- Actions ----------------------------------------------------------------

@pytest.mark.parametrize("label", REQUIRED_ACTIONS)
def test_the_plan_s_actions_are_present(label):
    assert label in {e["label"] for e in ENTRIES}, f"§4.2 requires {label!r}"


# --- Toggles ----------------------------------------------------------------

def test_every_toggle_declares_a_state_key():
    for entry in ENTRIES:
        if entry.get("ns") != "Toggles":
            continue
        assert entry.get("stateKey"), (
            f"the {entry['label']!r} toggle shows no state, so it cannot tell the "
            f"user which value it is in"
        )


def test_toggle_states_are_bound_to_the_real_stores():
    """The states object must read the store, not a local copy of it."""
    source = qml("components/CommandPalette.qml")
    body = source.split("readonly property var toggleStates: ({", 1)[1].split("})", 1)[0]
    keys = set(re.findall(r"(\w+):", body))
    declared = {e["stateKey"] for e in ENTRIES if e.get("ns") == "Toggles"}
    assert keys == declared, (
        f"toggleStates defines {sorted(keys)} but the toggles declare "
        f"{sorted(declared)}"
    )
    for key, store in TOGGLE_STORES.items():
        assert store in body, f"toggleStates[{key!r}] does not read {store}"


@pytest.mark.parametrize("key,store", sorted(TOGGLE_STORES.items()))
def test_invoking_a_toggle_writes_that_store(key, store):
    """Showing state is not enough — invoking must flip the same store."""
    body = qml("components/CommandPalette.qml").split("function _run(entry) {", 1)[1]
    body = body.split("\n    }", 1)[0]
    assert store in body, (
        f"the {key!r} toggle displays {store} but never writes it"
    )


# --- Jump-to-setting --------------------------------------------------------

def test_every_jump_target_exists_in_settings():
    """A jump to an objectName that does not exist scrolls nowhere, silently."""
    known = _settings_object_names()
    sections = set(_settings_sections())
    for entry in ENTRIES:
        if entry.get("action") != "jump":
            continue
        target = entry.get("target", "")
        if target:
            assert target in known, (
                f"{entry['label']!r} jumps to {target!r}, which no Settings control "
                f"is named"
            )
        assert entry.get("section") in sections, (
            f"{entry['label']!r} jumps to section {entry.get('section')!r}, which "
            f"SettingsPage does not have"
        )


def test_the_settings_page_can_resolve_a_jump():
    """The receiving half: clear the filter, switch section, then focus."""
    page = qml("pages/SettingsPage.qml")
    assert "function jumpTo(section, target, dialog)" in page
    body = page.split("function jumpTo(section, target, dialog) {", 1)[1].split("\n    }", 1)[0]
    assert "root.currentSection = section" in body
    assert "root.searchQuery" in body, (
        "a jump that does not clear the in-category filter cannot reach a row the "
        "filter hides"
    )
    assert "jumpTimer.restart()" in body, (
        "focusing a control whose card is still hidden is a no-op, so the focus "
        "must be deferred by one event-loop turn"
    )


# --- Fuzzy match ------------------------------------------------------------

@pytest.mark.parametrize("query,expected", [
    ("api key", "API key"),
    ("batch", "Batch size"),
    ("model path", "Local model path"),
])
def test_the_documented_queries_find_their_setting(query, expected):
    """The QML haystack is `label + ns + keywords`, lower-cased."""
    q = query.lower()
    hits = [
        e["label"] for e in ENTRIES
        if q in (e.get("label", "") + " " + e.get("ns", "") + " "
                 + e.get("keywords", "")).lower()
    ]
    assert expected in hits, (
        f"typing {query!r} does not reach {expected!r} (got {hits})"
    )


def test_the_match_haystack_includes_keywords_and_namespace():
    source = qml("components/CommandPalette.qml")
    assert 'c.label + " " + c.ns + " " + (c.keywords || "")' in source, (
        "the fuzzy match no longer covers keywords, so the documented jump "
        "queries stop working"
    )
