"""Content presets and one central, testable settings resolver."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ContentPreset:
    name: str
    description: str
    asr_preprocess: str
    asr_max_segment_ms: int
    asr_max_end_silence_ms: int
    asr_speech_noise_threshold: float
    asr_noise_db: float
    asr_min_silence_s: float
    asr_max_cue_duration_ms: int
    asr_max_cue_chars: int
    asr_max_cue_chars_cjk: int
    # None = defer to the backend default (light for local Hy-MT2,
    # standard for cloud) — only the auto preset uses None.
    context_mode: str | None
    prompt_profile: str
    max_line_chars: int
    max_cps: float


def _preset(name: str, description: str, preprocess: str, segment: int, silence: int,
            threshold: float, duration: int, cjk_chars: int, context: str | None,
            prompt: str) -> ContentPreset:
    return ContentPreset(name, description, preprocess, segment, silence, threshold,
                         -35.0, 0.25, duration, 70, cjk_chars, context, prompt, 40, 18.0)


PRESETS: dict[str, ContentPreset] = {
    # ``auto`` leaves context_mode unset: the engine then picks the
    # backend-appropriate default (light for local Hy-MT2, standard for cloud)
    # per plan §5.3. Named presets pin their context level explicitly.
    "auto": _preset("auto", "Balanced default behavior.", "basic", 6000, 250, 0.55, 3200, 48, None, "general"),
    "drama": _preset("drama", "Dialogue-driven drama.", "loudnorm", 5000, 230, 0.55, 4200, 30, "standard", "drama"),
    "anime": _preset("anime", "Fast animated dialogue.", "basic", 4000, 200, 0.62, 3800, 26, "standard", "anime"),
    "music": _preset("music", "Songs and music videos.", "basic", 6000, 300, 0.65, 5000, 28, "light", "music"),
    "documentary": _preset("documentary", "Narrated factual programming.", "loudnorm", 5500, 260, 0.52, 4800, 34, "deep", "documentary"),
    "variety": _preset("variety", "Fast multi-speaker programming.", "loudnorm", 4200, 220, 0.60, 3600, 26, "standard", "variety"),
    "lecture": _preset("lecture", "Long-form lecture or presentation.", "loudnorm", 6000, 300, 0.52, 5200, 36, "deep", "lecture"),
}


# Short, content-aware prompt addenda. These are APPENDED to the translation
# prompt (after the foreignization directive / Hy-MT2 style line) — they never
# replace the core directive. ``general`` (the auto preset) has no addendum.
PROMPT_ADDENDA: dict[str, str] = {
    "anime": (
        "Content note (anime): Preserve honorifics and culturally specific "
        "address terms unless the glossary says otherwise. Be careful with "
        "songs, sound effects, and abrupt speaker changes."
    ),
    "music": (
        "Content note (music): The source may be sung lyrics. Preserve "
        "emotional meaning and line rhythm. Do not over-explain; prefer "
        "concise singable phrasing when possible."
    ),
    "documentary": (
        "Content note (documentary): Use formal, clear narration-style "
        "English. Avoid slang and overly casual phrasing."
    ),
    "variety": (
        "Content note (variety show): Preserve rapid conversational tone, "
        "reactions, and humor. Do not flatten energetic speech into formal "
        "prose."
    ),
    "lecture": (
        "Content note (lecture): Prefer precise terminology and complete "
        "sentences. Maintain instructional clarity."
    ),
    "drama": (
        "Content note (drama): Keep dialogue natural and character-consistent; "
        "preserve interpersonal register and emotional subtext between scenes."
    ),
}


def get_prompt_addendum(prompt_profile: str | None) -> str | None:
    """Return the scoped addendum for a prompt profile (None = none)."""
    if not prompt_profile:
        return None
    return PROMPT_ADDENDA.get(str(prompt_profile).strip().lower())


_CONTROLLED = {
    "asr_preprocess": ("asr_preprocess", "FUNASR_PREPROCESS"),
    "asr_max_segment_ms": ("asr_max_segment_ms", "FUNASR_MAX_SEGMENT_MS"),
    "asr_max_end_silence_ms": ("asr_max_end_silence_ms", "FUNASR_MAX_END_SILENCE_MS"),
    "asr_speech_noise_threshold": ("asr_speech_noise_threshold", "FUNASR_SPEECH_NOISE_THRES"),
    "asr_noise_db": ("asr_noise_db", "FUNASR_NOISE_DB"),
    "asr_min_silence_s": ("asr_min_silence_s", "FUNASR_MIN_SILENCE_S"),
    "asr_max_cue_duration_ms": ("asr_max_cue_duration_ms", "FUNASR_MAX_CUE_DURATION_MS"),
    "asr_max_cue_chars": ("asr_max_cue_chars", "FUNASR_MAX_CUE_CHARS"),
    "asr_max_cue_chars_cjk": ("asr_max_cue_chars_cjk", "FUNASR_MAX_CUE_CHARS_CJK"),
    "context_mode": ("context_mode", "TRANSLATION_CONTEXT_MODE"),
    "prompt_profile": ("prompt_profile", "TRANSLATION_PROMPT_PROFILE"),
}


def resolve_effective_settings(args):
    """Apply explicit CLI > preset > environment > built-in precedence in place."""
    name = (getattr(args, "content_preset", "auto") or "auto").lower()
    if name not in PRESETS:
        raise ValueError(f"Unknown content preset: {name}")
    preset = PRESETS[name]
    defaults = PRESETS["auto"]
    for field, (arg_name, env_name) in _CONTROLLED.items():
        explicit = getattr(args, arg_name, None)
        if explicit is not None:
            continue
        env = os.environ.get(env_name)
        # Named content presets are deliberate product choices and therefore
        # outrank environment tuning. In Auto, environment remains the useful
        # deployment-level override over the built-in baseline.
        source = (
            getattr(preset, field)
            if name != "auto"
            else env if env not in (None, "") else getattr(defaults, field)
        )
        current = getattr(preset, field)
        if isinstance(current, int):
            source = int(source)
        elif isinstance(current, float):
            source = float(source)
        setattr(args, arg_name, source)
    return preset
