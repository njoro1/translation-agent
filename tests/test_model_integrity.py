"""Tests for model-state plumbing in AppBridge.

Covers the second half of the offline-flow bug: once a truncated GGUF is
detected, the app has to *report* it (so the user can repair it) and must not
hand the unusable path to the CLI, where it would fail minutes later with an
opaque ASR error.
"""
from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

import backend.bridge as bridge_module  # noqa: E402
from backend.bridge import (  # noqa: E402
    REMEDY_DOWNLOAD_MODEL,
    AppBridge,
    PIPELINE_MODE_OFFLINE,
    _ModelDownloadWorker,
    _classify_failure,
)
from tests.gguf_fixtures import build_gguf, write_gguf  # noqa: E402


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    """An AppBridge whose models folder is an empty temp directory.

    Patching ``_gguf_dir`` alone is not enough: ``_model_search_dirs()`` also
    returns ``_base_dir()`` and its ``gguf``/``models`` subfolders, which on a
    developer machine are the *real* repo folders holding real models. The
    fixture's "empty temp folder" then resolves to a complete model and every
    `missing` / `corrupt` assertion fails.
    """
    models = tmp_path / "gguf"
    models.mkdir()
    monkeypatch.setattr(bridge_module, "_gguf_dir", lambda: str(models))
    monkeypatch.setattr(bridge_module, "_model_search_dirs", lambda: [str(models)])
    instance = AppBridge()
    instance._settings.clear()
    instance._models_dir = models
    return instance


def _truncated(tmp_path, name: str) -> str:
    return write_gguf(tmp_path, name, truncate_bytes=64, tensors=2, elements=64)


# --- local translation model ------------------------------------------------


class TestLocalModelState:
    def test_reports_missing_when_nothing_is_there(self, bridge):
        assert bridge.localModelState == "missing"
        assert bridge.localModelReady is False
        assert bridge.localModelCorrupt is False

    def test_accepts_a_complete_model(self, bridge, tmp_path):
        path = write_gguf(tmp_path, "Hy-MT2-1.8B-Q8_0.gguf")
        bridge.localModel = path
        assert bridge.localModelState == "ready"
        assert bridge.localModelReady is True
        assert bridge.localModelCorrupt is False
        assert bridge.localModelProblem == ""

    def test_flags_a_truncated_model_as_corrupt(self, bridge, tmp_path):
        path = _truncated(tmp_path, "Hy-MT2-1.8B-Q8_0.gguf")
        bridge.localModel = path
        assert bridge.localModelState == "corrupt"
        assert bridge.localModelReady is False
        assert bridge.localModelCorrupt is True
        assert "incomplete" in bridge.localModelProblem
        assert "This file is incomplete" in bridge.localModelSelectionProblem

    def test_a_good_copy_in_the_models_folder_wins(self, bridge, tmp_path):
        """A stale corrupt selection must not mask a good downloaded model."""
        write_gguf(bridge._models_dir, "Hy-MT2-1.8B-Q8_0.gguf")
        bridge.localModel = _truncated(tmp_path, "elsewhere.gguf")
        assert bridge.localModelReady is True
        assert bridge.localModelCorrupt is False


# --- ASR models -------------------------------------------------------------


class TestAsrModelState:
    def test_requires_both_sensevoice_and_vad(self, bridge):
        write_gguf(bridge._models_dir, "sensevoice-small-q8.gguf")
        # VAD missing: transcription cannot run, so this is not "ready".
        assert bridge.asrModelState == "missing"
        assert bridge.asrModelReady is False

    def test_ready_when_both_models_are_complete(self, bridge):
        write_gguf(bridge._models_dir, "sensevoice-small-q8.gguf")
        write_gguf(bridge._models_dir, "fsmn-vad.gguf")
        assert bridge.asrModelState == "ready"
        assert bridge.asrModelReady is True

    def test_flags_a_truncated_sensevoice_model(self, bridge, tmp_path):
        path = _truncated(bridge._models_dir, "sensevoice-small-q8.gguf")
        write_gguf(bridge._models_dir, "fsmn-vad.gguf")
        bridge.asrModel = path
        assert bridge.asrModelState == "corrupt"
        assert bridge.asrModelReady is False
        assert bridge.asrModelCorrupt is True
        assert "SenseVoice" in bridge.asrModelProblem
        assert "incomplete" in bridge.asrModelProblem

    def test_falls_back_to_a_good_model_in_the_models_folder(self, bridge, tmp_path):
        write_gguf(bridge._models_dir, "sensevoice-small-q8.gguf")
        write_gguf(bridge._models_dir, "fsmn-vad.gguf")
        bridge.asrModel = _truncated(tmp_path, "stale.gguf")
        assert bridge.asrModelReady is True

    def test_a_bad_selection_is_still_reported_on_its_own(self, bridge, tmp_path):
        """The fallback keeps the run working; the Settings field still warns."""
        write_gguf(bridge._models_dir, "sensevoice-small-q8.gguf")
        write_gguf(bridge._models_dir, "fsmn-vad.gguf")
        bridge.asrModel = _truncated(tmp_path, "stale.gguf")

        assert bridge.asrModelReady is True
        assert bridge.asrModelProblem == ""
        assert "SenseVoice model is incomplete" in bridge.asrModelSelectionProblem
        assert "Re-download it" in bridge.asrModelSelectionProblem

    def test_no_selection_problem_when_the_paths_are_fine(self, bridge, tmp_path):
        good = write_gguf(tmp_path, "sensevoice-small-q8.gguf")
        bridge.asrModel = good
        assert bridge.asrModelSelectionProblem == ""
        assert bridge.localModelSelectionProblem == ""


# --- the models table -------------------------------------------------------


class TestModelsInventory:
    def test_marks_a_truncated_file_incomplete(self, bridge, tmp_path):
        write_gguf(bridge._models_dir, "sensevoice-small-q8.gguf", truncate_bytes=64,
                   tensors=2, elements=64)
        rows = {row["file"]: row for row in bridge.modelsInventory}
        assert rows["sensevoice-small-q8.gguf"]["state"] == "Incomplete"
        assert rows["sensevoice-small-q8.gguf"]["tone"] == "warn"
        # SIZE is bytes only — the folder tail used to be appended here and
        # painted over the PURPOSE column (UI review 5.4). The reason travels in
        # `note`, which the row renders on its own line.
        assert "incomplete" in rows["sensevoice-small-q8.gguf"]["note"].lower()
        assert "\\" not in rows["sensevoice-small-q8.gguf"]["size"]
        assert "/" not in rows["sensevoice-small-q8.gguf"]["size"]

    def test_marks_a_complete_file_verified(self, bridge):
        write_gguf(bridge._models_dir, "Hy-MT2-1.8B-Q8_0.gguf")
        rows = {row["file"]: row for row in bridge.modelsInventory}
        assert rows["Hy-MT2-1.8B-Q8_0.gguf"]["state"] == "Verified"
        assert rows["Hy-MT2-1.8B-Q8_0.gguf"]["tone"] == "ok"

    def test_marks_an_absent_file_missing(self, bridge):
        rows = {row["file"]: row for row in bridge.modelsInventory}
        assert rows["Hy-MT2-1.8B-Q8_0.gguf"]["state"] == "Missing"


# --- models left behind by the pre-onedir layout ----------------------------


@pytest.fixture
def frozen_bridge(tmp_path, monkeypatch):
    """An AppBridge in the frozen onedir layout, with the legacy sibling folder.

    ``<tmp>/dist/TranslationAgent/`` is the bundle (models folder empty);
    ``<tmp>/dist/gguf/`` holds models downloaded before the bundle moved.
    """
    bundle = tmp_path / "dist" / "TranslationAgent"
    bundle.mkdir(parents=True)
    models = bundle / "gguf"
    models.mkdir()
    legacy = tmp_path / "dist" / "gguf"
    legacy.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(bridge_module, "_base_dir", lambda: str(bundle))
    monkeypatch.setattr(bridge_module, "_gguf_dir", lambda: str(models))
    # Same isolation as the `bridge` fixture: the real repo folders must not be
    # searched, or a complete model there masks the temp layout under test.
    monkeypatch.setattr(
        bridge_module, "_model_search_dirs", lambda: [str(models), str(legacy)]
    )

    instance = AppBridge()
    instance._settings.clear()
    instance._models_dir = models
    instance._legacy_dir = legacy
    return instance


class TestLegacyModelsFolder:
    """Regression: the onedir move orphaned models the user already had.

    The bundle used to be written straight into ``dist/``, so downloads landed
    in ``dist/gguf/``. Moving to ``dist/TranslationAgent/`` moved the models
    folder, so those files became invisible, the app downloaded them again, and
    a second download onto a full disk was cut short — the truncated copy behind
    "FunASR produced no transcription". The user's report was literally "we
    already have the models downloaded".
    """

    def test_a_source_run_does_not_look_for_a_sibling_folder(self, bridge):
        assert bridge_module._legacy_gguf_dirs() == []

    def test_the_sibling_folder_is_searched_when_frozen(self, frozen_bridge):
        assert bridge_module._legacy_gguf_dirs() == [str(frozen_bridge._legacy_dir)]

    def test_models_in_the_legacy_folder_count_as_ready(self, frozen_bridge):
        write_gguf(frozen_bridge._legacy_dir, "sensevoice-small-q8.gguf")
        write_gguf(frozen_bridge._legacy_dir, "fsmn-vad.gguf")
        assert frozen_bridge.asrModelState == "ready"
        assert frozen_bridge.asrModelReady is True
        assert frozen_bridge.asrModelProblem == ""

    def test_a_truncated_legacy_copy_is_still_rejected(self, frozen_bridge):
        write_gguf(frozen_bridge._legacy_dir, "sensevoice-small-q8.gguf",
                   truncate_bytes=64, tensors=2, elements=64)
        write_gguf(frozen_bridge._legacy_dir, "fsmn-vad.gguf")
        assert frozen_bridge.asrModelState != "ready"
        assert frozen_bridge.asrModelReady is False

    def test_an_empty_asr_field_resolves_to_the_legacy_copy(
        self, frozen_bridge, tmp_path
    ):
        """The CLI's own fallback is cwd-relative, so the bridge must be explicit."""
        write_gguf(frozen_bridge._legacy_dir, "sensevoice-small-q8.gguf")
        write_gguf(frozen_bridge._legacy_dir, "fsmn-vad.gguf")
        frozen_bridge.pipelineMode = PIPELINE_MODE_OFFLINE
        frozen_bridge.filePath = str(tmp_path / "in.mp4")
        frozen_bridge.localModel = write_gguf(tmp_path, "Hy-MT2-1.8B-Q8_0.gguf")

        config = frozen_bridge._build_run_config()

        assert "--asr-model" in config.argv
        resolved = Path(config.argv[config.argv.index("--asr-model") + 1])
        assert resolved.parent == frozen_bridge._legacy_dir
        assert resolved.name == "sensevoice-small-q8.gguf"
        assert "--asr-vad-model" in config.argv

    def test_the_models_table_says_where_the_file_was_found(self, frozen_bridge):
        write_gguf(frozen_bridge._legacy_dir, "sensevoice-small-q8.gguf")
        rows = {row["file"]: row for row in frozen_bridge.modelsInventory}
        row = rows["sensevoice-small-q8.gguf"]
        assert row["state"] == "Verified"
        assert row["tone"] == "ok"
        # Otherwise "Verified" next to an empty models folder reads like a bug.
        # It says *where* in `note`, not in `size` (UI review 5.4).
        assert "dist" in row["note"]


# --- what the CLI is told ---------------------------------------------------


class TestRunConfigModelValidation:
    def test_unusable_asr_model_is_not_passed_to_the_cli(self, bridge, tmp_path):
        bridge.pipelineMode = PIPELINE_MODE_OFFLINE
        bridge.filePath = str(tmp_path / "in.mp4")
        bridge.localModel = write_gguf(tmp_path, "Hy-MT2-1.8B-Q8_0.gguf")
        bridge.asrModel = _truncated(tmp_path, "sensevoice-small-q8.gguf")

        config = bridge._build_run_config()

        assert "--asr-model" not in config.argv
        assert "Ignoring --asr-model" in bridge.logText

    def test_usable_asr_model_is_passed_through(self, bridge, tmp_path):
        bridge.pipelineMode = PIPELINE_MODE_OFFLINE
        bridge.filePath = str(tmp_path / "in.mp4")
        bridge.localModel = write_gguf(tmp_path, "Hy-MT2-1.8B-Q8_0.gguf")
        model = write_gguf(tmp_path, "sensevoice-small-q8.gguf")
        bridge.asrModel = model

        config = bridge._build_run_config()

        assert config.argv[config.argv.index("--asr-model") + 1] == model

    def test_corrupt_local_model_falls_back_to_the_models_folder(self, bridge, tmp_path):
        bridge.pipelineMode = PIPELINE_MODE_OFFLINE
        bridge.filePath = str(tmp_path / "in.mp4")
        good = write_gguf(bridge._models_dir, "Hy-MT2-1.8B-Q8_0.gguf")
        bridge.localModel = _truncated(tmp_path, "stale.gguf")

        config = bridge._build_run_config()

        assert config.argv[config.argv.index("--local-model") + 1] == good
        assert "is unusable" in bridge.logText

    def test_no_usable_model_at_all_fails_with_repair_guidance(self, bridge, tmp_path):
        bridge.pipelineMode = PIPELINE_MODE_OFFLINE
        bridge.filePath = str(tmp_path / "in.mp4")
        _truncated(bridge._models_dir, "Hy-MT2-1.8B-Q8_0.gguf")

        with pytest.raises(ValueError) as excinfo:
            bridge._build_run_config()

        message = str(excinfo.value)
        assert "No usable local translation model found" in message
        assert "incomplete" in message


# --- download worker --------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.length = len(payload)
        self._sent = False

    def read(self, _size: int) -> bytes:
        if self._sent:
            return b""
        self._sent = True
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _run_worker(monkeypatch, payload, urls):
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda url, *a, **k: _FakeResponse(payload)
    )
    worker = _ModelDownloadWorker(urls)
    worker.run()
    return worker


class TestModelDownloadWorker:
    def test_downloads_into_a_part_file_and_renames(self, bridge, monkeypatch):
        payload = build_gguf()
        worker = _run_worker(
            monkeypatch, payload, (("sensevoice-small-q8.gguf", "http://x/m.gguf"),)
        )
        dest = os.path.join(bridge._models_dir, "sensevoice-small-q8.gguf")
        assert worker.downloaded == [dest]
        assert os.path.getsize(dest) == len(payload)
        assert not os.path.exists(dest + ".part")

    def test_repairs_an_existing_truncated_file(self, bridge, monkeypatch):
        write_gguf(bridge._models_dir, "sensevoice-small-q8.gguf",
                   truncate_bytes=64, tensors=2, elements=64)
        payload = build_gguf()
        worker = _run_worker(
            monkeypatch, payload, (("sensevoice-small-q8.gguf", "http://x/m.gguf"),)
        )
        dest = os.path.join(bridge._models_dir, "sensevoice-small-q8.gguf")
        assert worker.downloaded == [dest]
        assert os.path.getsize(dest) == len(payload)

    def test_skips_a_file_that_is_already_complete(self, bridge, monkeypatch):
        write_gguf(bridge._models_dir, "fsmn-vad.gguf")

        def _explode(*_args, **_kwargs):
            raise AssertionError("a complete model must not be re-downloaded")

        monkeypatch.setattr(urllib.request, "urlopen", _explode)
        worker = _ModelDownloadWorker((("fsmn-vad.gguf", "http://x/m.gguf"),))
        worker.run()
        assert worker.downloaded == [os.path.join(bridge._models_dir, "fsmn-vad.gguf")]

    def test_a_failed_download_leaves_no_partial_file(self, bridge, monkeypatch):
        def _boom(*_args, **_kwargs):
            raise OSError("network down")

        monkeypatch.setattr(urllib.request, "urlopen", _boom)
        worker = _ModelDownloadWorker((("sensevoice-small-q8.gguf", "http://x/m.gguf"),))
        worker.run()

        assert worker.downloaded == []
        assert os.listdir(bridge._models_dir) == []

    def test_a_short_download_is_rejected_and_cleaned_up(self, bridge, monkeypatch):
        """A truncated payload must not be promoted to a real model file."""
        payload = build_gguf(tensors=2, elements=64)[:-64]
        worker = _run_worker(
            monkeypatch, payload, (("sensevoice-small-q8.gguf", "http://x/m.gguf"),)
        )
        assert worker.downloaded == []
        assert os.listdir(bridge._models_dir) == []


# --- failure classification -------------------------------------------------


class TestAsrFailureClassification:
    LOG = (
        "[asr] Preprocessing profile: basic\n"
        "error: FunASR produced no transcription. Check SenseVoice binary/model, "
        "try --asr-lang auto, or adjust VAD/silence thresholds.\n"
    )

    def test_no_transcription_is_not_reported_as_a_source_problem(self):
        code, title, _detail, remedy = _classify_failure(self.LOG)
        assert code == "ASR_MODEL"
        assert remedy == REMEDY_DOWNLOAD_MODEL
        assert "transcription" in title.lower() or "transcription model" in title.lower()
        assert "subtitle" not in title.lower()

    def test_a_genuinely_missing_youtube_transcript_still_maps_to_source(self):
        code, _title, _detail, remedy = _classify_failure(
            "ERROR: There are no subtitles for this video.\n"
        )
        assert code == "SOURCE_UNAVAILABLE"
        assert remedy == "check_source"

    def test_corrupt_model_output_maps_to_a_download(self):
        code, _title, _detail, remedy = _classify_failure(
            "gguf_init_from_reader: failed to read tensor data binary blob\n"
            "load gguf failed\n"
        )
        assert code == "ASR_MODEL"
        assert remedy == REMEDY_DOWNLOAD_MODEL


class TestAdvisoryLinesDoNotDriveClassification:
    """Regression: our own "[warn] Ignoring --asr-model …" line is not a failure.

    The line names a model file *and* the word "incomplete", so a naive pattern
    matched it and reported "The local transcription model could not be used."
    for runs that failed for an unrelated reason — or that succeeded.
    """

    IGNORE_WARNING = (
        "[warn] Ignoring --asr-model C:\\xampp\\htdocs\\translation-agent\\dist\\"
        "TranslationAgent\\gguf\\sensevoice-small-q8.gguf: file is incomplete: "
        "103213376 byte(s) short of the size its GGUF header describes. "
        "Falling back to the models folder.\n"
    )

    def test_an_unrelated_failure_is_not_blamed_on_the_ignored_model(self):
        code, _title, detail, remedy = _classify_failure(
            self.IGNORE_WARNING
            + "$ python translate.py --file clip.wav --local\n"
            + "[error] Media file not found: clip.wav\n"
        )
        assert code != "ASR_MODEL"
        assert remedy != REMEDY_DOWNLOAD_MODEL
        assert "clip.wav" in detail

    def test_the_ignore_warning_alone_never_classifies(self):
        code, _title, detail, remedy = _classify_failure(self.IGNORE_WARNING)
        assert code != "ASR_MODEL"
        assert remedy != REMEDY_DOWNLOAD_MODEL
        # The user still gets something concrete rather than an empty message.
        assert "sensevoice" in detail.lower()

    def test_a_real_corrupt_model_error_still_classifies(self):
        code, _title, _detail, remedy = _classify_failure(
            self.IGNORE_WARNING
            + "sensevoice-small-q8.gguf is incomplete (truncated)\n"
            "error: FunASR produced no transcription.\n"
        )
        assert code == "ASR_MODEL"
        assert remedy == REMEDY_DOWNLOAD_MODEL

    def test_a_path_mentioning_asr_does_not_classify(self):
        code, _title, _detail, remedy = _classify_failure(
            "$ python translate.py --asr-model C:\\models\\asr-missing-thing.gguf\n"
            "error: something else entirely went wrong\n"
        )
        assert code != "ASR_MODEL"
