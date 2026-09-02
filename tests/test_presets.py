from __future__ import annotations

import os
import types

import pytest

import translate
from src.presets import resolve_effective_settings


def test_anime_preset_resolves_unset_flags():
    args = translate._parse_args(["--content-preset", "anime"])
    resolve_effective_settings(args)
    assert args.asr_preprocess == "basic"
    assert args.asr_max_segment_ms == 4000
    assert args.asr_max_cue_chars_cjk == 26
    assert args.context_mode == "standard"


def test_explicit_flag_overrides_preset():
    args = translate._parse_args([
        "--content-preset", "anime", "--asr-max-segment-ms", "9000",
        "--context-mode", "off",
    ])
    resolve_effective_settings(args)
    assert args.asr_max_segment_ms == 9000
    assert args.context_mode == "off"


def test_environment_overrides_builtin_but_not_preset(monkeypatch):
    monkeypatch.setenv("FUNASR_MAX_SEGMENT_MS", "7777")
    args = translate._parse_args([])
    resolve_effective_settings(args)
    assert args.asr_max_segment_ms == 7777
    args = translate._parse_args(["--content-preset", "anime"])
    resolve_effective_settings(args)
    assert args.asr_max_segment_ms == 4000
    args = translate._parse_args(["--asr-max-segment-ms", "8888"])
    resolve_effective_settings(args)
    assert args.asr_max_segment_ms == 8888


def test_all_presets_match_plan_table():
    from src.presets import PRESETS

    expected = {
        # name: (preprocess, segment, silence, threshold, duration, cjk, context, prompt)
        # auto context is None = backend-deferred (light local / standard cloud).
        "auto": ("basic", 6000, 250, 0.55, 3200, 48, None, "general"),
        "drama": ("loudnorm", 5000, 230, 0.55, 4200, 30, "standard", "drama"),
        "anime": ("basic", 4000, 200, 0.62, 3800, 26, "standard", "anime"),
        "music": ("basic", 6000, 300, 0.65, 5000, 28, "light", "music"),
        "documentary": ("loudnorm", 5500, 260, 0.52, 4800, 34, "deep", "documentary"),
        "variety": ("loudnorm", 4200, 220, 0.60, 3600, 26, "standard", "variety"),
        "lecture": ("loudnorm", 6000, 300, 0.52, 5200, 36, "deep", "lecture"),
    }
    assert set(PRESETS) == set(expected)
    for name, row in expected.items():
        p = PRESETS[name]
        got = (
            p.asr_preprocess, p.asr_max_segment_ms, p.asr_max_end_silence_ms,
            p.asr_speech_noise_threshold, p.asr_max_cue_duration_ms,
            p.asr_max_cue_chars_cjk, p.context_mode, p.prompt_profile,
        )
        assert got == row, name


def test_unknown_preset_fails_cleanly():
    import types

    args = types.SimpleNamespace(content_preset="telenovela")
    with pytest.raises(ValueError, match="Unknown content preset"):
        resolve_effective_settings(args)


def test_prompt_profile_resolves_from_preset():
    args = translate._parse_args(["--content-preset", "documentary"])
    resolve_effective_settings(args)
    assert args.prompt_profile == "documentary"
    args = translate._parse_args([])
    resolve_effective_settings(args)
    assert args.prompt_profile == "general"
