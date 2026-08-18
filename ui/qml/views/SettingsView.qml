import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "../components"

Item {
    id: root

    ScrollView {
        anchors.fill: parent
        anchors.margins: 24
        clip: true

        ColumnLayout {
            width: parent.width
            spacing: 18

            Label {
                text: "Settings"
                color: "#f8fafc"
                font.pixelSize: 24
                font.bold: true
            }

            Label {
                Layout.fillWidth: true
                text: "Configure the translation backend and local ASR runtime. Changes here apply to the next run."
                color: "#94a3b8"
                wrapMode: Text.WordWrap
                font.pixelSize: 13
            }

            Card {
                Layout.fillWidth: true
                title: "Translation Backend"
                subtitle: "Configure the translation engine for the selected pipeline mode. The Dashboard controls which flow is active."

                Label {
                    Layout.fillWidth: true
                    text: "Active pipeline: " + (
                        appBridge.pipelineMode === "youtube" ? "YouTube \u2192 Cloud" :
                        appBridge.pipelineMode === "local_hybrid" ? "Local \u2192 Local + AI fallback" :
                        "Local \u2192 Local only (offline)"
                    )
                    color: "#cbd5e1"
                    font.pixelSize: 12
                }

                Label {
                    Layout.fillWidth: true
                    text: "Backend: " + (appBridge.backend === "cloud" ? "Cloud API" : "Local llama.cpp")
                    color: "#94a3b8"
                    font.pixelSize: 11
                }

                Label {
                    Layout.fillWidth: true
                    visible: appBridge.backend === "local"
                    text: appBridge.cloudRescueEnabled ? "Cloud rescue: enabled" : "Cloud rescue: disabled"
                    color: appBridge.cloudRescueEnabled ? "#6366f1" : "#64748b"
                    font.pixelSize: 11
                    font.italic: true
                }

                ColumnLayout {
                    visible: appBridge.backend === "cloud"
                    Layout.fillWidth: true
                    spacing: 10

                    Label {
                        text: "API key"
                        color: "#cbd5e1"
                        font.pixelSize: 12
                    }

                    CustomTextField {
                        Layout.fillWidth: true
                        echoMode: TextInput.Password
                        placeholderText: "OpenAI-compatible key"
                        text: appBridge.apiKey
                        onTextEdited: appBridge.apiKey = text
                    }

                    Label {
                        text: "Base URL"
                        color: "#cbd5e1"
                        font.pixelSize: 12
                    }

                    CustomTextField {
                        Layout.fillWidth: true
                        placeholderText: "https://api.openai.com/v1"
                        text: appBridge.baseUrl
                        onTextEdited: appBridge.baseUrl = text
                    }

                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: "Must be an OpenAI-compatible API root, e.g. https://api.openai.com/v1 (or http://127.0.0.1:8080/v1 for the local server). Pointing it at a website/home page returns HTTP 404/405 \u2014 not an LLM."
                        color: "#94a3b8"
                        font.pixelSize: 11
                    }

                    Label {
                        text: "Model"
                        color: "#cbd5e1"
                        font.pixelSize: 12
                    }

                    CustomTextField {
                        Layout.fillWidth: true
                        placeholderText: "gpt-4o-mini"
                        text: appBridge.model
                        onTextEdited: appBridge.model = text
                    }
                }

                ColumnLayout {
                    visible: appBridge.backend === "local"
                    Layout.fillWidth: true
                    spacing: 10

                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: "The local llama-server is launched automatically on http://127.0.0.1:8080/v1. You do not need to configure host/port manually."
                        color: "#64748b"
                        font.pixelSize: 11
                    }

                    Label {
                        text: "Model name"
                        color: "#cbd5e1"
                        font.pixelSize: 12
                    }

                    CustomTextField {
                        Layout.fillWidth: true
                        text: appBridge.modelName
                        onTextEdited: appBridge.modelName = text
                    }

                    Label {
                        text: "Translation model (.gguf)"
                        color: "#cbd5e1"
                        font.pixelSize: 12
                    }

                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        visible: appBridge.backend === "local" && !appBridge.localModelReady
                        text: "\u26a0 No translation model found. Click Download to fetch Hy-MT2-1.8B-Q8_0.gguf, or Browse to select an existing GGUF. Local runs cannot start without it."
                        color: "#f59e0b"
                        font.pixelSize: 11
                    }

                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        visible: appBridge.backend === "local" && appBridge.localModelReady
                        text: appBridge.localModelReady
                            ? "\u2713 Translation model is available" + (appBridge.localModel.trim() ? " (" + (appBridge.localModel.includes("/") || appBridge.localModel.includes("\\") ? appBridge.localModel.split(/[\\/]/).pop() : appBridge.localModel) + ")" : " (auto-detected in the app's gguf folder)")
                            : ""
                        color: "#22c55e"
                        font.pixelSize: 11
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            CustomTextField {
                                Layout.fillWidth: true
                                placeholderText: "Hy-MT2-1.8B-Q8_0.gguf"
                                text: appBridge.localModel
                                onTextEdited: appBridge.localModel = text
                            }

                            Label {
                                text: "The app auto-starts bundled llama-server (CPU) against this file on each run. Download it once, or point at a GGUF you already have."
                                color: "#94a3b8"
                                font.pixelSize: 11
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }

                            Label {
                                visible: appBridge.localModelDownloadStatus.length > 0
                                text: appBridge.localModelDownloadStatus.trim().split("\n").pop()
                                color: "#94a3b8"
                                font.pixelSize: 11
                                elide: Label.ElideLeft
                                Layout.fillWidth: true
                            }
                        }

                        Button {
                            text: appBridge.localModelDownloading ? "Downloading…"
                                : appBridge.localModelReady ? "Re-download"
                                : "Download model"
                            enabled: !appBridge.localModelDownloading
                            onClicked: appBridge.downloadLocalModel()
                        }

                        Button {
                            text: "Browse"
                            onClicked: localModelDialog.open()
                        }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                title: "Local ASR"
                subtitle: "Uses the FunASR + SenseVoiceSmall CPU runtime. Configure the binaries, models, and timing below; local files are transcribed into short, well-paced subtitle cues (no large text blocks)."

                Label {
                    text: "SenseVoice binary"
                    color: "#cbd5e1"
                    font.pixelSize: 12
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    CustomTextField {
                        Layout.fillWidth: true
                        text: appBridge.asrBin
                        onTextEdited: appBridge.asrBin = text
                    }

                    Button {
                        text: "Browse"
                        onClicked: asrBinDialog.open()
                    }
                }

                Label {
                    text: "VAD binary"
                    color: "#cbd5e1"
                    font.pixelSize: 12
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    CustomTextField {
                        Layout.fillWidth: true
                        text: appBridge.asrVadBin
                        onTextEdited: appBridge.asrVadBin = text
                    }

                    Button {
                        text: "Browse"
                        onClicked: asrVadBinDialog.open()
                    }
                }

                Label {
                    text: "SenseVoice model"
                    color: "#cbd5e1"
                    font.pixelSize: 12
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    CustomTextField {
                        Layout.fillWidth: true
                        text: appBridge.asrModel
                        onTextEdited: appBridge.asrModel = text
                    }

                    Button {
                        text: "Browse"
                        onClicked: asrModelDialog.open()
                    }
                }

                Label {
                    text: "VAD model"
                    color: "#cbd5e1"
                    font.pixelSize: 12
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    CustomTextField {
                        Layout.fillWidth: true
                        text: appBridge.asrVadModel
                        onTextEdited: appBridge.asrVadModel = text
                    }

                    Button {
                        text: "Browse"
                        onClicked: asrVadModelDialog.open()
                    }
                }

                Label {
                    text: "ASR language"
                    color: "#cbd5e1"
                    font.pixelSize: 12
                }

                ComboBox {
                    Layout.fillWidth: true
                    model: [
                        { label: "Auto-detect", code: "auto" },
                        { label: "Chinese", code: "zh" },
                        { label: "English", code: "en" },
                        { label: "Japanese", code: "ja" },
                        { label: "Korean", code: "ko" },
                        { label: "Cantonese", code: "yue" }
                    ]
                    textRole: "label"
                    currentIndex: {
                        for (let i = 0; i < model.length; ++i) {
                            if (model[i].code === appBridge.asrLanguage) {
                                return i
                            }
                        }
                        return 0
                    }
                    onActivated: appBridge.asrLanguage = model[index].code
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 10

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "ASR threads"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrThreads
                            onTextEdited: appBridge.asrThreads = text
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Max segment ms"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrMaxSegmentMs
                            onTextEdited: appBridge.asrMaxSegmentMs = text
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Max end silence ms"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrMaxEndSilenceMs
                            onTextEdited: appBridge.asrMaxEndSilenceMs = text
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Speech/noise threshold"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrSpeechNoiseThreshold
                            onTextEdited: appBridge.asrSpeechNoiseThreshold = text
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Noise dB"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrNoiseDb
                            onTextEdited: appBridge.asrNoiseDb = text
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Minimum silence seconds"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrMinSilenceS
                            onTextEdited: appBridge.asrMinSilenceS = text
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Max cue duration ms"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrMaxCueDurationMs
                            onTextEdited: appBridge.asrMaxCueDurationMs = text
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Max cue chars (CJK)"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrMaxCueCharsCjk
                            onTextEdited: appBridge.asrMaxCueCharsCjk = text
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Max cue chars"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrMaxCueChars
                            onTextEdited: appBridge.asrMaxCueChars = text
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    CheckBox {
                        text: "Keep ASR tags (disable default stripping)"
                        checked: appBridge.asrKeepTags
                        onCheckedChanged: appBridge.asrKeepTags = checked
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4

                        Label {
                            text: "Models are stored in the app's gguf folder."
                            color: "#94a3b8"
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        Label {
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                            visible: appBridge.localModelReady || appBridge.asrModelReady
                            text: (appBridge.asrModelReady ? "\u2713 SenseVoice + VAD models found in the app's gguf folder." : "\u26a0 ASR models not found yet.")
                            color: appBridge.asrModelReady ? "#22c55e" : "#f59e0b"
                            font.pixelSize: 11
                        }

                        Label {
                            visible: appBridge.modelDownloadStatus.length > 0
                            text: appBridge.modelDownloadStatus.trim().split("\n").pop()
                            color: "#94a3b8"
                            font.pixelSize: 11
                            elide: Label.ElideLeft
                            Layout.fillWidth: true
                        }
                    }

                    Button {
                        text: appBridge.modelDownloading ? "Downloading…"
                            : appBridge.asrModelReady ? "Re-download"
                            : "Download models"
                        enabled: !appBridge.modelDownloading
                        onClicked: appBridge.downloadAsrModels()
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                title: "Advanced / Quality"
                subtitle: "Optional quality and consistency aids. Translation memory and glossary improve consistency; cloud rescue can recover failed local cues."

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Glossary file"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            placeholderText: "Path to glossary.txt"
                            text: appBridge.glossaryPath
                            onTextEdited: appBridge.glossaryPath = text
                        }
                    }

                    Button {
                        text: "Browse…"
                        onClicked: glossaryDialog.open()
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Translation memory"; color: "#cbd5e1"; font.pixelSize: 12 }
                        ComboBox {
                            Layout.fillWidth: true
                            model: ["auto", "on", "off"]
                            currentIndex: {
                                var v = appBridge.translationMemoryMode
                                return v === "on" ? 1 : (v === "off" ? 2 : 0)
                            }
                            onActivated: appBridge.translationMemoryMode = currentText
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Local server threads (0 = auto)"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.localThreads
                            onTextEdited: appBridge.localThreads = text
                        }
                    }
                }

RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Label { text: "Output format"; color: "#cbd5e1"; font.pixelSize: 12 }
                        ComboBox {
                            Layout.fillWidth: true
                            model: ["srt", "ass"]
                            currentIndex: appBridge.outputFormat === "ass" ? 1 : 0
                            onActivated: appBridge.outputFormat = currentText
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    CheckBox {
                        text: "Use mlock for local server"
                        checked: appBridge.localMlock
                        onCheckedChanged: appBridge.localMlock = checked
                    }

                    CheckBox {
                        text: "Strict quality (fail on errors)"
                        checked: appBridge.strictQuality
                        onCheckedChanged: appBridge.strictQuality = checked
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    CheckBox {
                        text: "Cloud rescue"
                        checked: appBridge.cloudRescueEnabled
                        onCheckedChanged: appBridge.cloudRescueEnabled = checked
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        enabled: appBridge.cloudRescueEnabled
                        Label { text: "Cloud rescue model"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            placeholderText: "gpt-4o-mini"
                            text: appBridge.cloudRescueModel
                            onTextEdited: appBridge.cloudRescueModel = text
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        enabled: appBridge.cloudRescueEnabled
                        Label { text: "Rescue batch"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.cloudRescueBatch
                            onTextEdited: appBridge.cloudRescueBatch = text
                        }
                    }
                }
            }
        }
    }

    FileDialog {
        id: asrBinDialog
        title: "Select SenseVoice binary"
        nameFilters: ["Executables (*.exe)", "All files (*)"]
        onAccepted: appBridge.asrBin = appBridge.localPath(selectedFile.toString())
    }

    FileDialog {
        id: asrVadBinDialog
        title: "Select VAD binary"
        nameFilters: ["Executables (*.exe)", "All files (*)"]
        onAccepted: appBridge.asrVadBin = appBridge.localPath(selectedFile.toString())
    }

    FileDialog {
        id: asrModelDialog
        title: "Select SenseVoice model"
        nameFilters: ["GGUF files (*.gguf)", "All files (*)"]
        onAccepted: appBridge.asrModel = appBridge.localPath(selectedFile.toString())
    }

    FileDialog {
        id: asrVadModelDialog
        title: "Select VAD model"
        nameFilters: ["GGUF files (*.gguf)", "All files (*)"]
        onAccepted: appBridge.asrVadModel = appBridge.localPath(selectedFile.toString())
    }

    FileDialog {
        id: localModelDialog
        title: "Select local translation model"
        nameFilters: ["GGUF files (*.gguf)", "All files (*)"]
        onAccepted: appBridge.localModel = appBridge.localPath(selectedFile.toString())
    }

    FileDialog {
        id: glossaryDialog
        title: "Select glossary file"
        nameFilters: ["Text files (*.txt)", "All files (*)"]
        onAccepted: appBridge.glossaryPath = appBridge.localPath(selectedFile.toString())
    }
}
