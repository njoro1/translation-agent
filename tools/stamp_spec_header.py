"""Stamp the generated-file banner onto PyInstaller's spec output.

Why this exists
---------------
``TranslationAgent.spec`` is *generated output*, not source. ``build_exe.bat``
drives PyInstaller entirely from command-line flags, and PyInstaller rewrites
the spec from those flags on every build. Anything hand-added to the file —
including a "do not edit" comment — is destroyed by the next build.

That makes the banner self-defeating if it lives only in the spec: it vanishes
exactly when a new contributor is most likely to open the freshly written file
and start editing it. Stamping it *after* the build, from the build script,
means the warning is always present in the file on disk and its wording is
owned by one place.

Anchoring the paths to this file's own location (rather than the current
working directory) matters because ``build_exe.bat`` calls this with a
relative path via ``%~dp0``; the script must not depend on where it is run
from.

Invoked by ``build_exe.bat`` as::

    python tools\\stamp_spec_header.py TranslationAgent.spec

Exit codes: 0 on success (including the benign "already stamped" case),
1 on a genuine failure so the caller can warn.
"""
from __future__ import annotations

import sys
from pathlib import Path

HEADER_MARKER = "GENERATED FILE"

HEADER = '''# ===========================================================================
# GENERATED FILE — do not hand-edit.
#
# PyInstaller rewrites this spec from the command-line flags in
# build_exe.bat on every build, so any edit made here is silently
# discarded the next time the project is rebuilt.
#
# To change the build, edit build_exe.bat instead. If you add a new Qt
# import to the source, add the matching --hidden-import there; the trimmed
# PySide6 module list means an undeclared Qt module is simply absent from
# the bundle, and the app will fail to load its QML at runtime.
#
# tools/stamp_spec_header.py re-applies this banner after each build.
# ===========================================================================
'''


def stamp(spec_path: Path) -> int:
    """Prepend HEADER to *spec_path*; idempotent."""
    if not spec_path.is_file():
        print(f"stamp_spec_header: no such file: {spec_path}", file=sys.stderr)
        return 1

    try:
        text = spec_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"stamp_spec_header: cannot read {spec_path}: {exc}", file=sys.stderr)
        return 1

    if HEADER_MARKER in text:
        print("stamp_spec_header: banner already present, nothing to do")
        return 0

    # Keep any leading coding declaration on line 1: Python requires it to be
    # in the first two lines, so a banner above it would break the encoding
    # declaration and make the spec unparseable.
    lines = text.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines[:2]):
        if line.startswith("#") and "coding" in line:
            insert_at = i + 1
            break
    else:
        if lines and lines[0].startswith("#!"):
            insert_at = 1

    stamped = "".join(lines[:insert_at]) + HEADER + "".join(lines[insert_at:])

    try:
        spec_path.write_text(stamped, encoding="utf-8")
    except OSError as exc:
        print(f"stamp_spec_header: cannot write {spec_path}: {exc}", file=sys.stderr)
        return 1

    print(f"stamp_spec_header: banner applied to {spec_path.name}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: stamp_spec_header.py <path-to-spec>", file=sys.stderr)
        return 1
    spec = Path(argv[1])
    if not spec.is_absolute():
        # build_exe.bat cd's to the project root, but resolve relative to the
        # caller's cwd explicitly so manual runs behave the same way.
        spec = Path.cwd() / spec
    return stamp(spec)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
