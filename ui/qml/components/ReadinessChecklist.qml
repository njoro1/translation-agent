import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Pre-run readiness checklist for the currently selected mode.
ColumnLayout {
    id: root

    spacing: Theme.xs

    function _sourceReady() {
        if (appBridge.pipelineMode === "youtube_cloud")
            return appBridge.url.trim() !== ""
        return appBridge.filePath.trim() !== ""
    }

    function _backendReady() {
        if (appBridge.pipelineMode === "offline")
            return appBridge.localModelReady
        return true  // cloud: blank fields fall back to .env / defaults
    }

    function _asrReady() {
        if (appBridge.pipelineMode === "youtube_cloud")
            return true  // no ASR needed
        return appBridge.asrModelReady
    }

    function _outputReady() {
        return true  // empty output path auto-derives from the title
    }

    Repeater {
        model: [
            { label: "Source selected", ok: root._sourceReady(),
              hint: appBridge.pipelineMode === "youtube_cloud"
                    ? "Enter a YouTube URL" : "Choose a local media file" },
            { label: "ASR model available", ok: root._asrReady(),
              hint: "Download the SenseVoice model for local transcription" },
            { label: "Translation backend ready", ok: root._backendReady(),
              hint: appBridge.pipelineMode === "offline"
                    ? "Download or select a local translation model"
                    : "Set an API key in Advanced, or rely on .env" },
            { label: "Output path valid", ok: root._outputReady(),
              hint: "Leave blank to auto-name from the title" }
        ]

        delegate: RowLayout {
            required property var modelData
            spacing: Theme.sm

            Label {
                text: modelData.ok ? "\u2713" : "\u00D7"
                color: modelData.ok ? Theme.success : Theme.warning
                font.pixelSize: Theme.fontBody
                font.bold: true
            }

            Label {
                text: modelData.label
                color: modelData.ok ? Theme.text : Theme.textMuted
                font.pixelSize: Theme.fontBody
            }

            Label {
                visible: !modelData.ok
                text: "\u2014 " + modelData.hint
                color: Theme.textMuted
                font.pixelSize: Theme.fontSmall
                elide: Text.ElideRight
                Layout.maximumWidth: 220
            }
        }
    }
}
