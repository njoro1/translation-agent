import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.srt_io import read_srt


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if len(sys.argv) < 2:
        print("Usage: python tools/check_srt.py output.srt")
        raise SystemExit(1)

    path = Path(sys.argv[1])
    cues = read_srt(path)

    if not cues:
        print("No cues found.")
        return

    durations = [c.end - c.start for c in cues]

    print(f"file: {path}")
    print(f"cues: {len(cues)}")
    print(f"average duration: {sum(durations) / len(durations):.3f}s")
    print(f"max duration: {max(durations):.3f}s")
    print(f"min duration: {min(durations):.3f}s")

    long_cues = [c for c in cues if (c.end - c.start) > 6.0]
    print(f"cues longer than 6s: {len(long_cues)}")

    for c in long_cues[:10]:
        print(f"  {c.start:.3f} -> {c.end:.3f}: {c.text[:80]}")


if __name__ == "__main__":
    main()
