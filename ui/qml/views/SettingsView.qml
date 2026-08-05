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
                subtitle: "Use a hosted OpenAI-compatible endpoint, or a local GGUF model auto-served by the app's bundled llama.cpp server (no manual server setup)."

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    StyledRadioButton {
                        checked: appBridge.backend === "cloud"
                        text: "Cloud API"
                        onClicked: appBridge.backend = "cloud"
                    }

                    StyledRadioButton {
                        checked: appBridge.backend === "local"
                        text: "Local llama.cpp"
                        onClicked: appBridge.backend = "local"
                    }
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

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        ColumnLayout {
                            Layout.fillWidth: true

                            Label {
                                text: "Host"
                                color: "#cbd5e1"
                                font.pixelSize: 12
                            }

                            CustomTextField {
                                Layout.fillWidth: true
                                text: appBridge.host
                                onTextEdited: appBridge.host = text
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true

                            Label {
                                text: "Port"
                                color: "#cbd5e1"
                                font.pixelSize: 12
                            }

                            CustomTextField {
                                Layout.fillWidth: true
                                text: appBridge.port
                                validator: IntValidator { bottom: 1 }
                                onTextEdited: appBridge.port = text
                            }
                        }
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

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            CustomTextField {
                                Layout.fillWidth: true
                                placeholderText: "Hy-MT2-1.8B-1.25Bit.gguf"
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
                            text: appBridge.localModelDownloading ? "Downloading…" : "Download"
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
                        Label { text: "Max cue chars"; color: "#cbd5e1"; font.pixelSize: 12 }
                        CustomTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrMaxCueChars
                            onTextEdited: appBridge.asrMaxCueChars = text
                        }
                    }
                }

                CheckBox {
                    text: "No tags"
                    checked: appBridge.asrNoTags
                    onCheckedChanged: appBridge.asrNoTags = checked
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
                            visible: appBridge.modelDownloadStatus.length > 0
                            text: appBridge.modelDownloadStatus.trim().split("\n").pop()
                            color: "#94a3b8"
                            font.pixelSize: 11
                            elide: Label.ElideLeft
                            Layout.fillWidth: true
                        }
                    }

                    Button {
                        text: appBridge.modelDownloading ? "Downloading…" : "Download models"
                        enabled: !appBridge.modelDownloading
                        onClicked: appBridge.downloadAsrModels()
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
}
