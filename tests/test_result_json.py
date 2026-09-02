"""End-to-end CLI tests for --result-json (Phase 2) and final-line contract."""
from __future__ import annotations

import json

import pytest

import translate
from src.srt_io import Cue


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _FakeClient:
    """Answers every numbered request with aligned English lines."""

    def __init__(self):
        self.calls = 0

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.calls += 1
        user = [
            m["content"] for m in kwargs.get("messages", [])
            if m.get("role") == "user"
        ][-1]
        import re

        items = {}
        for line in user.splitlines():
            m = re.match(r"^\s*(\d+)\.\s?(.*)$", line)
            if m:
                items[int(m.group(1))] = f"translation {m.group(1)}"
        return _Resp("\n".join(f"{i}. {t}" for i, t in sorted(items.items())))


@pytest.fixture()
def patched_pipeline(monkeypatch):
    def _install(cues):
        monkeypatch.setattr(
            translate, "fetch_original_subtitles",
            lambda url, preferred_lang=None: (cues, "Test Video", "ja"),
        )
        settings = type("S", (), {"model": "test-model"})()
        monkeypatch.setattr(translate, "load_settings", lambda override_model=None: settings)
        monkeypatch.setattr(translate, "make_client", lambda settings: _FakeClient())

    return _install


def test_result_json_written_before_final_line(patched_pipeline, tmp_path, capsys):
    cues = [Cue(0.0, 0.9, "一"), Cue(1.0, 1.9, "二"), Cue(2.0, 2.9, "三")]
    patched_pipeline(cues)

    out_path = tmp_path / "out.srt"
    result_path = tmp_path / "result.json"
    rc = translate.main([
        "https://youtu.be/x",
        "--out", str(out_path),
        "--result-json", str(result_path),
        "--context-mode", "off",
        "--batch", "4",
    ])
    assert rc == 0

    # Final line contract preserved and comes after everything else.
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert lines[-1] == f"Wrote 3 cues to {out_path}"

    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["output_path"] == str(out_path)
    assert data["format"] == "srt"
    assert data["source_language"] == "ja"
    assert data["pipeline_mode"] == "youtube_cloud"
    assert data["strict_quality"] is False
    assert "quality" in data and data["quality"]["cue_count"] == 3
    assert len(data["cues"]) == 3
    first = data["cues"][0]
    assert first["index"] == 1
    assert first["start_ms"] == 0 and first["end_ms"] == 900
    assert first["source"] == "一"
    assert first["text"] == "translation 1"
    assert first["status"] == "ok"


def test_result_json_flags_untranslated(patched_pipeline, tmp_path):
    from src.translate import TranslationEndpointError  # noqa: F401

    class _RejectClient(_FakeClient):
        def create(self, **kwargs):
            return _Resp("")  # always empty -> per-item also fails -> ""

    cues = [Cue(0.0, 1.0, "一"), Cue(1.0, 2.0, "二")]

    def _install(cues_):
        pass

    # Reuse fixture machinery but swap in the failing client.
    monkey_target = patched_pipeline
    cues_ = cues
    monkey_target(cues_)
    # Override the client factory with the rejecting one.
    import translate as t

    settings = type("S", (), {"model": "test-model"})()
    t.load_settings = lambda override_model=None: settings
    t.make_client = lambda settings: _RejectClient()

    out_path = tmp_path / "out2.srt"
    result_path = tmp_path / "result2.json"
    rc = t.main([
        "https://youtu.be/x",
        "--out", str(out_path),
        "--result-json", str(result_path),
        "--context-mode", "off",
    ])
    assert rc == 0  # failures are flagged, not fatal (no --strict-quality)

    data = json.loads(result_path.read_text(encoding="utf-8"))
    assert len(data["cues"]) == 2
    assert all(c["text"] == "[untranslated]" for c in data["cues"])
    assert all(c["status"] == "untranslated" for c in data["cues"])
    assert data["quality"]["untranslated_count"] == 2


def test_no_result_json_flag_keeps_cli_behavior(patched_pipeline, tmp_path, capsys):
    cues = [Cue(0.0, 1.0, "一")]
    patched_pipeline(cues)
    out_path = tmp_path / "solo.srt"
    rc = translate.main([
        "https://youtu.be/x", "--out", str(out_path), "--context-mode", "off",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[result]" not in out
    assert out.strip().splitlines()[-1] == f"Wrote 1 cues to {out_path}"
