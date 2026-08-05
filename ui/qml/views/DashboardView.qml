import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "../components"

Item {
    id: root

    function labelForAsr(code) {
        if (code === "zh") return "Chinese"
        if (code === "en") return "English"
        if (code === "ja") return "Japanese"
        if (code === "ko") return "Korean"
        if (code === "yue") return "Cantonese"
        return "Auto-detect"
    }

    SplitView {
        anchors.fill: parent
        orientation: Qt.Horizontal
        handle: Rectangle {
            implicitWidth: 1
            color: "#1f2937"
        }

        Rectangle {
            SplitView.preferredWidth: 340
            SplitView.minimumWidth: 300
            color: "#0b1220"
            border.color: "#1f2937"
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 24
                spacing: 18

                Label {
                    text: "Translation Control"
                    color: "#f8fafc"
                    font.pixelSize: 24
                    font.bold: true
                }

                Label {
                    Layout.fillWidth: true
                    text: "Move between YouTube subtitle translation and local media transcription from one polished desktop shell."
                    color: "#94a3b8"
                    wrapMode: Text.WordWrap
                    font.pixelSize: 13
                }

                Rectangle {
                    Layout.fillWidth: true
                    radius: 16
                    color: "#111827"
                    border.color: "#312e81"
                    border.width: 1
                    implicitHeight: statusInner.implicitHeight + 32

                    ColumnLayout {
                        id: statusInner
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 10

                        Label {
                            text: "Session Status"
                            color: "#cbd5e1"
                            font.pixelSize: 12
                            font.bold: true
                        }

                        Label {
                            Layout.fillWidth: true
                            text: appBridge.statusMessage
                            color: "#ffffff"
                            wrapMode: Text.WordWrap
                            font.pixelSize: 16
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    radius: 16
                    color: "#111827"
                    border.color: "#27272a"
                    border.width: 1
                    implicitHeight: summaryInner.implicitHeight + 32

                    ColumnLayout {
                        id: summaryInner
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 10

                        Label {
                            text: "Source"
                            color: "#94a3b8"
                            font.pixelSize: 11
                        }

                        Label {
                            text: appBridge.mode === "youtube" ? "YouTube URL" : "Local media file"
                            color: "#f8fafc"
                            font.pixelSize: 14
                            font.bold: true
                        }

                        Label {
                            text: "Backend"
                            color: "#94a3b8"
                            font.pixelSize: 11
                        }

                        Label {
                            text: appBridge.backend === "cloud" ? "Cloud API" : "Local llama.cpp"
                            color: "#f8fafc"
                            font.pixelSize: 14
                            font.bold: true
                        }

                        Label {
                            text: "Batch Size"
                            color: "#94a3b8"
                            font.pixelSize: 11
                        }

                        Label {
                            text: appBridge.batch
                            color: "#f8fafc"
                            font.pixelSize: 14
                            font.bold: true
                        }

                        Label {
                            text: "ASR Language"
                            color: "#94a3b8"
                            font.pixelSize: 11
                        }

                        Label {
                            text: root.labelForAsr(appBridge.asrLanguage)
                            color: "#f8fafc"
                            font.pixelSize: 14
                            font.bold: true
                        }
                    }
                }

                Item {
                    Layout.fillHeight: true
                }

                Label {
                    Layout.fillWidth: true
                    text: "Pipeline runs unchanged on the CLI backend; this UI wraps it in a hardware-accelerated shell."
                    color: "#64748b"
                    wrapMode: Text.WordWrap
                    font.pixelSize: 12
                }
            }
        }

        Item {
            SplitView.fillWidth: true
            SplitView.minimumWidth: 680

            ScrollView {
                anchors.fill: parent
                anchors.margins: 24
                clip: true

                ColumnLayout {
                    width: parent.width
                    spacing: 18

                    Card {
                        Layout.fillWidth: true
                        title: "Source"
                        subtitle: "Choose an existing YouTube subtitle track or transcribe a local media file before translation."

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            StyledRadioButton {
                                checked: appBridge.mode === "youtube"
                                text: "YouTube URL"
                                onClicked: appBridge.mode = "youtube"
                            }

                            StyledRadioButton {
                                checked: appBridge.mode === "file"
                                text: "Local file"
                                onClicked: appBridge.mode = "file"
                            }
                        }

                        Label {
                            visible: appBridge.mode === "youtube"
                            text: "YouTube video URL"
                            color: "#cbd5e1"
                            font.pixelSize: 12
                        }

                        CustomTextField {
                            visible: appBridge.mode === "youtube"
                            Layout.fillWidth: true
                            placeholderText: "https://youtube.com/watch?v=..."
                            text: appBridge.url
                            onTextEdited: appBridge.url = text
                        }

                        Label {
                            visible: appBridge.mode === "file"
                            text: "Local video or audio file"
                            color: "#cbd5e1"
                            font.pixelSize: 12
                        }

                        RowLayout {
                            visible: appBridge.mode === "file"
                            Layout.fillWidth: true
                            spacing: 10

                            CustomTextField {
                                Layout.fillWidth: true
                                placeholderText: "Select a .mp4, .mkv, .wav, .mp3..."
                                text: appBridge.filePath
                                onTextEdited: appBridge.filePath = text
                            }

                            Button {
                                text: "Browse"
                                onClicked: inputFileDialog.open()
                            }
                        }

                        Label {
                            visible: appBridge.mode === "file"
                            text: "Spoken language"
                            color: "#cbd5e1"
                            font.pixelSize: 12
                        }

                        Label {
                            visible: appBridge.mode === "file"
                            Layout.fillWidth: true
                            text: "Used by local transcription and as the translation source language."
                            color: "#64748b"
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                        }

                        ComboBox {
                            visible: appBridge.mode === "file"
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
                    }

                    Card {
                        Layout.fillWidth: true
                        title: "Output"
                        subtitle: "Leave the subtitle path empty to derive the filename from the source title."

                        Label {
                            text: "SRT output path"
                            color: "#cbd5e1"
                            font.pixelSize: 12
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            CustomTextField {
                                Layout.fillWidth: true
                                placeholderText: "Optional .srt output path"
                                text: appBridge.outPath
                                onTextEdited: appBridge.outPath = text
                            }

                            Button {
                                text: "Save As"
                                onClicked: outputFileDialog.open()
                            }
                        }

                        Label {
                            text: "Batch size"
                            color: "#cbd5e1"
                            font.pixelSize: 12
                        }

                        CustomTextField {
                            Layout.fillWidth: true
                            placeholderText: "40"
                            text: appBridge.batch
                            validator: IntValidator { bottom: 1 }
                            onTextEdited: appBridge.batch = text
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        title: "Execution Log"
                        subtitle: "The CLI pipeline still runs unchanged, but its output now streams through the Qt bridge in real time."

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                PrimaryButton {
                                    text: appBridge.isRunning ? "Running..." : "Run Translation"
                                    enabled: !appBridge.isRunning
                                    onClicked: appBridge.runTranslation()
                                }

                                Button {
                                    text: "Open Output Folder"
                                    enabled: appBridge.canOpenOutputFolder
                                    onClicked: appBridge.openOutputFolder()
                                }

                                Button {
                                    text: "Clear Log"
                                    enabled: !appBridge.isRunning
                                    onClicked: appBridge.clearLog()
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 260
                                Layout.fillHeight: true
                                radius: 16
                                color: "#09090b"
                                border.color: "#27272a"
                                border.width: 1

                                ScrollView {
                                    anchors.fill: parent
                                    anchors.margins: 1
                                    clip: true

                                    TextArea {
                                        id: logArea
                                        text: appBridge.logText
                                        readOnly: true
                                        wrapMode: TextArea.WrapAnywhere
                                        color: "#e4e4e7"
                                        selectByMouse: true
                                        font.family: "Consolas"
                                        font.pixelSize: 12
                                        background: Rectangle {
                                            color: "#09090b"
                                            radius: 15
                                        }

                                        onTextChanged: cursorPosition = length
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    FileDialog {
        id: inputFileDialog
        title: "Select video or audio file"
        nameFilters: ["Media files (*.mp4 *.mkv *.webm *.mov *.avi *.mp3 *.wav *.m4a *.flac)", "All files (*)"]
        onAccepted: appBridge.filePath = appBridge.localPath(selectedFile.toString())
    }

    FileDialog {
        id: outputFileDialog
        title: "Save subtitle file"
        fileMode: FileDialog.SaveFile
        nameFilters: ["SRT subtitles (*.srt)", "All files (*)"]
        defaultSuffix: "srt"
        onAccepted: appBridge.outPath = appBridge.localPath(selectedFile.toString())
    }
}
