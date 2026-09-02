from __future__ import annotations

from pathlib import Path

import pytest

from src import local_asr


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("none", None),
        ("basic", "highpass=f=80"),
        ("loudnorm", "highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11:linear=true"),
        ("denoise", "highpass=f=80,afftdn=nf=-25:tn=true,loudnorm=I=-16:TP=-1.5:LRA=11:linear=true"),
    ],
)
def test_preprocess_profiles_have_expected_filters(profile, expected):
    assert local_asr._preprocess_filter(profile) == expected


def test_auto_resolves_to_basic():
    assert local_asr._resolve_preprocess_profile("auto") == "basic"


def test_invalid_preprocess_profile_is_rejected():
    with pytest.raises(ValueError, match="Invalid ASR preprocessing profile"):
        local_asr._resolve_preprocess_profile("destructive")


def test_duration_mismatch_falls_back_to_none(monkeypatch, tmp_path):
    calls: list[str] = []
    durations = iter([1.2, 1.2, 1.0])

    monkeypatch.setattr(local_asr, "_media_duration", lambda path: 1.0)
    monkeypatch.setattr(local_asr, "_wav_duration", lambda path: next(durations))
    monkeypatch.setattr(
        local_asr,
        "_extract_wav",
        lambda media, output, profile: calls.append(profile),
    )

    output = local_asr._prepare_asr_audio(Path("input.mp4"), tmp_path / "audio.wav", "loudnorm")
    assert output == tmp_path / "audio.wav"
    assert calls == ["loudnorm", "basic", "none"]
