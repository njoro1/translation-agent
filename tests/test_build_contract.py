"""The packaged build has no automated test — so check its *contract* instead.

A full `build_exe.bat` run (PyInstaller, ~2 min, hundreds of MB) is far too
heavy for the suite. But almost everything that actually breaks a frozen build
is a *declaration* problem, and those are cheap to verify:

  * `build_exe.bat` hard-codes vendor binaries and data directories it expects
    to exist. If one is missing or renamed, the build has no way to succeed.
  * It lists `--hidden-import` modules. PyInstaller only bundles what it can
    resolve, so a stale name (a module that was renamed or deleted) silently
    drops code out of the exe.
  * It hard-codes a trimmed list of PySide6 modules, and the comments say to
    extend it when new Qt imports appear. Nothing enforced that — a new
    `PySide6.QtXxx` import would surface only as a runtime crash in the exe.

These tests read the real script, so they fail if the script drifts rather than
if this file drifts.
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "build_exe.bat"
SPEC = ROOT / "TranslationAgent.spec"


def _script_text() -> str:
    assert BUILD_SCRIPT.is_file(), "build_exe.bat is missing"
    return BUILD_SCRIPT.read_text(encoding="utf-8", errors="replace")


def _continued_command(text: str) -> str:
    """Join the PyInstaller invocation, which is split with `^` line ends."""
    return text.replace("^\n", " ").replace("^\r\n", " ")


def _vendor_checks(text: str) -> list[str]:
    """Paths guarded by ``if not exist "<path>"`` in the build script."""
    return re.findall(r'if not exist "([^"]+)"', text)


def _add_flags(text: str) -> list[tuple[str, str]]:
    """Every ``--add-data/--add-binary "src;dest"`` source and destination."""
    joined = _continued_command(text)
    found = re.findall(r'--add-(?:data|binary)\s+"([^"]+)"', joined)
    pairs = []
    for item in found:
        # A Windows drive letter ("C:\...") contains a colon but is not a
        # src;dest separator, so split on the *last* separator only.
        src, _, dest = item.rpartition(";")
        if not src:
            src, dest = item, ""
        pairs.append((src, dest))
    return pairs


def _hidden_imports(text: str) -> list[str]:
    joined = _continued_command(text)
    return re.findall(r"--hidden-import\s+([A-Za-z_][\w.]*)", joined)


def _pyside6_imports_in_source() -> set[str]:
    """Top-level PySide6 submodules imported anywhere in first-party code."""
    pattern = re.compile(r"^\s*(?:from|import)\s+(PySide6\.\w+)", re.MULTILINE)
    found: set[str] = set()
    for folder in ("backend", "src", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            found.update(pattern.findall(
                path.read_text(encoding="utf-8", errors="replace")))
    for name in ("main.py", "gui.py", "translate.py"):
        path = ROOT / name
        if path.is_file():
            found.update(pattern.findall(
                path.read_text(encoding="utf-8", errors="replace")))
    return found


class TestBuildInputsExist:
    """A missing input makes a build impossible; catch it in seconds."""

    def test_build_script_exists(self):
        assert BUILD_SCRIPT.is_file()

    def test_every_guarded_path_exists(self):
        text = _script_text()
        guarded = [p for p in _vendor_checks(text)
                   if not p.lower().startswith("dist")]
        assert guarded, "expected the script to guard its vendor binaries"
        missing = [p for p in guarded if not (ROOT / p.replace("\\", "/")).exists()]
        assert not missing, (
            "build_exe.bat requires these paths and they are absent: "
            f"{missing}")

    def test_every_add_data_source_exists(self):
        missing = [
            src for src, _dest in _add_flags(_script_text())
            # %VAR%-based sources are resolved by the script at build time.
            if "%" not in src and not (ROOT / src.replace("\\", "/")).exists()
        ]
        assert not missing, f"--add-data/--add-binary sources missing: {missing}"

    def test_entry_point_exists(self):
        assert (ROOT / "main.py").is_file()


class TestHiddenImportsResolve:
    """A stale --hidden-import silently drops code out of the exe."""

    @staticmethod
    def _resolvable(module: str) -> bool:
        try:
            return importlib.util.find_spec(module) is not None
        except (ImportError, AttributeError, ValueError):
            return False

    def test_every_hidden_import_resolves(self):
        modules = _hidden_imports(_script_text())
        assert modules, "no --hidden-import flags found in build_exe.bat"
        # Third-party packages that legitimately live outside the repo are
        # skipped when absent, so the suite still runs on a bare checkout.
        unresolvable = [m for m in modules if not self._resolvable(m)]
        assert not unresolvable, (
            f"--hidden-import targets that cannot be resolved: {unresolvable}")

    def test_runtime_critical_modules_are_declared(self):
        """The modules a frozen build *cannot* discover on its own."""
        modules = set(_hidden_imports(_script_text()))
        required = {
            "src.youtube_media",   # our download/inspect path
            "src.ytdlp",           # in-process yt-dlp launcher
            "backend.bridge",      # the QML bridge
            "src.local_asr",
            "src.local_server",
            "yt_dlp",              # pulls in its own PyInstaller hook
            "openai",
            "dotenv",
        }
        assert required <= modules, f"not declared: {sorted(required - modules)}"

    def test_qt_modules_imported_by_source_are_declared(self):
        """New `PySide6.QtXxx` imports must be added to the trimmed bundle.

        The build deliberately ships only the Qt modules the app uses, so a
        module that is imported but not declared becomes a crash *inside the
        packaged exe* — the one place tests never run.
        """
        declared = set(_hidden_imports(_script_text()))
        used = _pyside6_imports_in_source()
        missing = {m for m in used - declared
                   if m.startswith("PySide6.Qt")}
        assert not missing, (
            "these PySide6 modules are imported by the app but not bundled; add "
            f"--hidden-import for each: {sorted(missing)}")


class TestSpecIsGeneratedNotAuthored:
    """`build_exe.bat` drives the build from CLI flags, not from the spec.

    PyInstaller writes the effective config back out to the .spec after each
    run, which is why the committed copy carries absolute paths from the last
    build machine. Treating it as a build input leads to pointless edits that
    the next build overwrites.
    """

    def test_spec_is_not_passed_to_pyinstaller(self):
        """Detect the spec being *given to PyInstaller*, not merely named.

        An earlier version of this check asserted the literal ".spec" was
        absent, which broke the moment the build script legitimately mentioned
        the spec elsewhere (the stamper invocation). What matters is the
        PyInstaller command line, so the flags are inspected directly.
        """
        command = _continued_command(_script_text())
        assert "python -m PyInstaller" in command, (
            "could not find the PyInstaller invocation in build_exe.bat")
        invocation = command.split("python -m PyInstaller", 1)[1].split("\n", 1)[0]
        assert "TranslationAgent.spec" not in invocation, (
            "build_exe.bat started passing the spec to PyInstaller as input — "
            "the notes in AGENT_DOCUMENTATION.md about it being generated are "
            f"now wrong. Offending invocation: {invocation.strip()}"
        )

    def test_spec_header_warns_that_it_is_generated(self):
        assert SPEC.is_file()
        head = SPEC.read_text(encoding="utf-8", errors="replace")[:600]
        assert "GENERATED FILE" in head, (
            "the spec needs its do-not-hand-edit header")
        assert "do not hand-edit" in head

    def test_spec_is_still_valid_python(self):
        """A marker comment must never break PyInstaller's re-parse."""
        ast.parse(SPEC.read_text(encoding="utf-8", errors="replace"))

    def test_build_script_reapplies_the_header_after_building(self):
        """The header cannot live *only* in the spec.

        PyInstaller rewrites the spec from the CLI flags on every build, so a
        hand-added banner is destroyed by the next run. If the build script
        does not re-stamp it, the file that a contributor opens after a fresh
        build is the one with no warning in it — precisely backwards.
        """
        text = _script_text()
        assert "stamp_spec_header.py" in text, (
            "build_exe.bat must re-apply the generated-file banner after "
            "PyInstaller rewrites the spec")
        # The stamp must run after the build, not before it (it would be
        # overwritten otherwise).
        assert text.index("stamp_spec_header.py") > text.index("python -m PyInstaller"), (
            "the stamp runs before the build — PyInstaller would overwrite it")

    def test_build_is_machine_portable(self):
        """Guard the whole point of the notes: the *script* must resolve its
        inputs dynamically rather than hard-coding one machine's paths."""
        text = _script_text()
        assert "python -c" in text, (
            "build_exe.bat should resolve PySide6/ffmpeg via python -c so the "
            "build works on any machine")
        for env_var in ("PYSIDE6_DIR", "FFMPEG_EXE"):
            assert env_var in text, f"{env_var} is no longer resolved at build time"


class TestStampSpecHeaderTool:
    """The stamper is build machinery, so it gets tests like any other code."""

    @pytest.fixture()
    def stamper(self):
        import importlib.util

        path = ROOT / "tools" / "stamp_spec_header.py"
        assert path.is_file(), "tools/stamp_spec_header.py is missing"
        spec = importlib.util.spec_from_file_location("stamp_spec_header", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_keeps_the_coding_declaration_on_line_one(self, stamper, tmp_path):
        """Python only honours an encoding declaration in the first two lines,
        so the banner must go *below* it or the spec stops parsing."""
        target = tmp_path / "TranslationAgent.spec"
        original = "# -*- mode: python ; coding: utf-8 -*-\n\na = Analysis(['main.py'])\n"
        target.write_text(original, encoding="utf-8")

        assert stamper.stamp(target) == 0

        lines = target.read_text(encoding="utf-8").splitlines()
        assert "coding: utf-8" in lines[0], f"declaration moved: {lines[0]!r}"
        assert "GENERATED FILE" in "\n".join(lines[:12])

    def test_stamped_spec_is_still_valid_python(self, stamper, tmp_path):
        target = tmp_path / "TranslationAgent.spec"
        target.write_text(
            "# -*- mode: python ; coding: utf-8 -*-\n\na = Analysis(['main.py'])\n",
            encoding="utf-8")
        assert stamper.stamp(target) == 0
        ast.parse(target.read_text(encoding="utf-8"))

    def test_is_idempotent(self, stamper, tmp_path):
        """build_exe.bat may run twice; a second banner would be noise."""
        target = tmp_path / "TranslationAgent.spec"
        target.write_text("# -*- mode: python ; coding: utf-8 -*-\nx = 1\n",
                          encoding="utf-8")
        assert stamper.stamp(target) == 0
        once = target.read_text(encoding="utf-8")

        assert stamper.stamp(target) == 0
        assert target.read_text(encoding="utf-8") == once, "double-stamped"

    def test_reports_a_missing_file_instead_of_raising(self, stamper, tmp_path):
        assert stamper.stamp(tmp_path / "nope.spec") == 1

    def test_missing_argument_is_a_usage_error(self, stamper):
        assert stamper.main(["stamp_spec_header.py"]) == 1

    def test_live_spec_carries_the_banner(self, stamper):
        """End-to-end on the real file, without rewriting it."""
        text = SPEC.read_text(encoding="utf-8", errors="replace")
        assert stamper.HEADER_MARKER in text[:600], (
            "the committed spec lost its banner — run "
            "python tools/stamp_spec_header.py TranslationAgent.spec")
