"""Client-machine usability: model discovery, Browse pickers, output location.

Three things broke the app on a machine that is not the build machine:

1. Models had to be guessed into one exact folder. A client who copies the
   ``.gguf`` files next to ``TranslationAgent.exe`` — the layout the bundle
   implies — got "models missing".
2. There was no way to *pick* a model: the Settings rows were free-text path
   boxes, which is unusable on a client machine.
3. Subtitles were written to the process working directory instead of beside
   the video they came from.

These tests pin the behaviour that fixes all three.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

import backend.bridge as bridge_module  # noqa: E402
import translate  # noqa: E402
from backend.bridge import AppBridge  # noqa: E402
from tests.gguf_fixtures import write_gguf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_QML = ROOT / "ui" / "qml" / "pages" / "SettingsPage.qml"
RUN_QML = ROOT / "ui" / "qml" / "pages" / "RunPage.qml"


# ===========================================================================
# 1. Where the subtitles land
# ===========================================================================


class TestDefaultOutputPath:
    """`--out` omitted must not mean "wherever the process happens to be"."""

    def test_local_file_writes_beside_it(self, tmp_path):
        video = tmp_path / "clips" / "talk.mp4"
        assert translate.default_output_path(str(video), "", "srt") == str(
            tmp_path / "clips" / "talk.srt"
        )

    def test_extension_follows_the_format(self, tmp_path):
        video = tmp_path / "a.mkv"
        assert translate.default_output_path(str(video), "", "ass").endswith("a.ass")

    def test_dotted_names_keep_only_the_last_extension(self, tmp_path):
        video = tmp_path / "show.s01e02.mkv"
        assert Path(
            translate.default_output_path(str(video), "", "srt")
        ).name == "show.s01e02.srt"

    def test_unsafe_characters_are_sanitised(self, tmp_path):
        video = tmp_path / "a:b?c.mp4"
        name = Path(translate.default_output_path(str(video), "", "srt")).name
        assert ":" not in name and "?" not in name

    def test_youtube_run_keeps_the_title_name(self):
        result = translate.default_output_path(None, "My Video", "srt")
        assert Path(result).name == "My Video.srt"

    def test_youtube_run_without_a_title_still_writes_something(self):
        assert Path(translate.default_output_path(None, "", "srt")).name == "subtitles.srt"


class TestBridgeAutoOutputPath:
    @pytest.fixture()
    def bridge(self):
        instance = AppBridge()
        instance._settings.clear()
        return instance

    def test_starts_blank_and_on_auto(self, bridge):
        assert bridge.outPathAuto is True
        assert bridge.outPath == ""

    def test_picking_a_video_fills_the_path_next_to_it(self, bridge, tmp_path):
        video = tmp_path / "talk.mp4"
        bridge.filePath = str(video)
        assert bridge.outPath == str(tmp_path / "talk.srt")
        assert bridge.outPathAuto is True

    def test_changing_the_format_moves_the_auto_path(self, bridge, tmp_path):
        bridge.filePath = str(tmp_path / "talk.mp4")
        bridge.outputFormat = "ass"
        assert bridge.outPath == str(tmp_path / "talk.ass")

    def test_a_typed_path_wins_and_sticks(self, bridge, tmp_path):
        bridge.filePath = str(tmp_path / "talk.mp4")
        bridge.outPath = str(tmp_path / "custom.srt")
        assert bridge.outPathAuto is False
        # Changing the video must not silently overwrite a deliberate choice.
        bridge.filePath = str(tmp_path / "other.mp4")
        assert bridge.outPath == str(tmp_path / "custom.srt")

    def test_clearing_the_field_returns_to_auto(self, bridge, tmp_path):
        bridge.filePath = str(tmp_path / "talk.mp4")
        bridge.outPath = str(tmp_path / "custom.srt")
        bridge.outPath = ""
        assert bridge.outPathAuto is True
        assert bridge.outPath == str(tmp_path / "talk.srt")

    def test_use_auto_out_path_restores_the_default(self, bridge, tmp_path):
        bridge.filePath = str(tmp_path / "talk.mp4")
        bridge.outPath = str(tmp_path / "custom.srt")
        bridge.useAutoOutPath()
        assert bridge.outPath == str(tmp_path / "talk.srt")

    def test_removing_the_video_clears_the_auto_path(self, bridge, tmp_path):
        bridge.filePath = str(tmp_path / "talk.mp4")
        bridge.filePath = ""
        assert bridge.outPath == ""

    def test_hint_explains_the_destination(self, bridge, tmp_path):
        bridge.filePath = str(tmp_path / "talk.mp4")
        assert "next to the video" in bridge.outPathHint.lower()

    def test_readiness_row_reports_the_derived_folder(self, bridge, tmp_path):
        bridge.filePath = str(tmp_path / "talk.mp4")
        row = next(r for r in bridge.readinessRows if r["id"] == "output")
        assert row["state"] == "ok"
        assert row["hint"] == "Next to the video"


# ===========================================================================
# 2. Where the app looks for models
# ===========================================================================


@pytest.fixture()
def fake_layout(tmp_path, monkeypatch):
    """A frozen-style layout: an app folder plus a per-user fallback folder."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    data_dir = tmp_path / "userdata"
    data_dir.mkdir()
    monkeypatch.setattr(bridge_module, "_base_dir", lambda: str(app_dir))
    monkeypatch.setattr(bridge_module, "_app_data_dir", lambda: str(data_dir))
    return app_dir, data_dir


class TestModelSearchDirs:
    def test_the_exe_folder_is_searched_first(self, fake_layout):
        app_dir, _data = fake_layout
        assert Path(bridge_module._model_search_dirs()[0]) == app_dir

    def test_gguf_and_models_subfolders_are_searched(self, fake_layout):
        app_dir, _data = fake_layout
        dirs = {Path(d).name for d in bridge_module._model_search_dirs()}
        assert {"gguf", "models"} <= dirs

    def test_the_per_user_folder_is_the_last_resort(self, fake_layout):
        _app_dir, data_dir = fake_layout
        assert data_dir / "gguf" in [Path(d) for d in bridge_module._model_search_dirs()]

    def test_no_folder_is_searched_twice(self, fake_layout):
        dirs = [str(Path(d)) for d in bridge_module._model_search_dirs()]
        assert len(dirs) == len(set(dirs))

    def test_a_model_dropped_next_to_the_exe_is_found(self, fake_layout):
        app_dir, _data = fake_layout
        write_gguf(app_dir, "Hy-MT2-1.8B-Q8_0.gguf")
        found = bridge_module._find_local_model()
        assert Path(found) == app_dir / "Hy-MT2-1.8B-Q8_0.gguf"

    def test_a_model_in_the_gguf_subfolder_is_found(self, fake_layout):
        app_dir, _data = fake_layout
        (app_dir / "gguf").mkdir()
        write_gguf(app_dir / "gguf", "sensevoice-small-q8.gguf")
        found = bridge_module._find_model_file("sensevoice-small-q8.gguf")
        assert Path(found) == app_dir / "gguf" / "sensevoice-small-q8.gguf"

    def test_a_truncated_file_is_not_mistaken_for_a_model(self, fake_layout):
        app_dir, _data = fake_layout
        write_gguf(app_dir, "Hy-MT2-1.8B-Q8_0.gguf", truncate_bytes=64)
        assert bridge_module._find_local_model() == ""


class TestWritableFallback:
    def test_a_read_only_app_folder_falls_back_to_the_user_folder(
        self, fake_layout, monkeypatch
    ):
        app_dir, data_dir = fake_layout
        monkeypatch.setattr(bridge_module, "_is_writable_dir", lambda _p: False)
        assert Path(bridge_module._gguf_dir()) == data_dir / "gguf"

    def test_a_writable_app_folder_keeps_models_beside_the_exe(self, fake_layout):
        app_dir, _data = fake_layout
        assert Path(bridge_module._gguf_dir()) == app_dir / "gguf"

    def test_the_result_cache_follows_the_same_rule(self, fake_layout, monkeypatch):
        _app_dir, data_dir = fake_layout
        monkeypatch.setattr(bridge_module, "_is_writable_dir", lambda _p: False)
        assert Path(bridge_module._result_json_path()).parent == data_dir / "cache"

    def test_is_writable_dir_rejects_a_missing_folder(self, tmp_path):
        assert bridge_module._is_writable_dir(str(tmp_path / "nope")) is False

    def test_is_writable_dir_accepts_a_real_folder(self, tmp_path):
        assert bridge_module._is_writable_dir(str(tmp_path)) is True


class TestModelSearchPathsProperty:
    @pytest.fixture()
    def bridge(self, fake_layout):
        instance = AppBridge()
        instance._settings.clear()
        return instance

    def test_rows_describe_every_search_folder(self, bridge):
        rows = bridge.modelSearchPaths
        assert rows, "Settings needs at least one row to show the user"
        assert {r["path"] for r in rows} == {
            str(Path(p)) for p in bridge_module._model_search_dirs()
        }

    def test_exactly_one_row_is_marked_as_the_download_target(self, bridge):
        assert sum(1 for r in bridge.modelSearchPaths if r["primary"]) == 1

    def test_the_download_row_is_the_models_folder(self, bridge):
        primary = next(r for r in bridge.modelSearchPaths if r["primary"])
        assert Path(primary["path"]) == Path(bridge.modelsFolder)


# ===========================================================================
# 3. The pickers themselves
# ===========================================================================


class TestFileDialogHelpers:
    @pytest.fixture()
    def bridge(self):
        instance = AppBridge()
        instance._settings.clear()
        return instance

    def test_folder_url_points_at_the_containing_folder(self, bridge, tmp_path):
        video = tmp_path / "talk.mp4"
        assert bridge.folderUrl(str(video)).startswith("file:///")
        assert bridge.folderUrl(str(video)).endswith("talk.mp4") is False
        assert str(tmp_path).split("\\")[-1] in bridge.folderUrl(str(video))

    def test_folder_url_is_blank_for_an_unknown_path(self, bridge):
        assert bridge.folderUrl("") == ""

    def test_file_url_points_at_the_file(self, bridge, tmp_path):
        video = tmp_path / "talk.mp4"
        assert bridge.fileUrl(str(video)).endswith("talk.mp4")

    def test_file_url_is_blank_for_an_empty_path(self, bridge):
        assert bridge.fileUrl("") == ""

    def test_last_input_dir_follows_the_picked_video(self, bridge, tmp_path):
        video = tmp_path / "clips" / "talk.mp4"
        video.parent.mkdir()
        bridge.filePath = str(video)
        assert Path(bridge.lastInputDir) == video.parent


class TestPickerWiring:
    """Source-level checks: a dialog nothing opens is a dead Browse button."""

    def _text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "dialog",
        [
            "localModelDialog",
            "asrModelDialog",
            "asrVadModelDialog",
            "asrBinDialog",
            "asrVadBinDialog",
        ],
    )
    def test_every_dialog_is_defined_and_opened(self, dialog):
        text = self._text(SETTINGS_QML)
        assert f"id: {dialog}" in text, f"{dialog} is missing"
        assert f"{dialog}.open()" in text, f"{dialog} is never opened"

    def test_every_model_path_row_has_a_browse_button(self):
        text = self._text(SETTINGS_QML)
        assert text.count('text: "Browse"') >= 5, (
            "each model/binary path row needs its own Browse button"
        )

    def test_picked_paths_are_written_back_to_the_bridge(self):
        text = self._text(SETTINGS_QML)
        for prop in ("localModel", "asrModel", "asrVadModel", "asrBin", "asrVadBin"):
            assert f"appBridge.{prop} = appBridge.localPath(selectedFile)" in text, (
                f"the {prop} picker does not store its selection"
            )

    def test_the_output_row_offers_a_way_back_to_auto(self):
        text = self._text(RUN_QML)
        assert "appBridge.useAutoOutPath()" in text

    def test_the_output_placeholder_no_longer_lies(self):
        text = self._text(RUN_QML)
        assert "Auto-named from the title" not in text
        assert "Saved next to the video" in text

    def test_the_input_picker_opens_where_the_user_already_is(self):
        text = self._text(RUN_QML)
        assert "currentFolder: appBridge.folderUrl(appBridge.lastInputDir)" in text
