from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from backend.bridge import (
    AppBridge,
    PIPELINE_MODE_LOCAL_CLOUD,
    PIPELINE_MODE_OFFLINE,
    PIPELINE_MODE_YOUTUBE_CLOUD,
)


def _bridge() -> AppBridge:
    bridge = AppBridge()
    bridge._settings.clear()
    return bridge


def test_youtube_cloud_uses_url_and_cloud_environment():
    bridge = _bridge()
    bridge.pipelineMode = PIPELINE_MODE_YOUTUBE_CLOUD
    bridge.url = "https://example.test/watch?v=1"
    bridge.sourceLang = "ja"
    bridge.apiKey = "key"
    config = bridge._build_run_config()
    assert config.argv[:3] == [bridge.url, "--source-lang", "ja"]
    assert "--file" not in config.argv and "--local" not in config.argv
    assert config.env == {"OPENAI_API_KEY": "key"}


def test_local_cloud_uses_file_and_never_local_translation():
    bridge = _bridge()
    bridge.pipelineMode = PIPELINE_MODE_LOCAL_CLOUD
    bridge.filePath = "video.mp4"
    bridge.apiKey = "key"
    config = bridge._build_run_config()
    assert config.argv[:2] == ["--file", "video.mp4"]
    assert "--local" not in config.argv
    assert config.env == {"OPENAI_API_KEY": "key"}


def test_offline_uses_local_translation_and_strips_cloud_environment(monkeypatch):
    bridge = _bridge()
    bridge.pipelineMode = PIPELINE_MODE_OFFLINE
    bridge.filePath = "video.mp4"
    bridge.localModel = "model.gguf"
    bridge.apiKey = "key"
    bridge.baseUrl = "https://example.test/v1"
    config = bridge._build_run_config()
    assert "--local" in config.argv
    assert config.env == {}
