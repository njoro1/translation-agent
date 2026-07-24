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

                    ColumnLayout {
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

                    GridLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        columns: 2
                        columnSpacing: 10
                        rowSpacing: 10

                        Rectangle {
                            Layout.fillWidth: true
                            radius: 12
                            color: "#18181b"
                            border.color: "#27272a"
                            implicitHeight: 74

                            Column {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 6

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
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: 12
                            color: "#18181b"
                            border.color: "#27272a"
                            implicitHeight: 74

                            Column {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 6

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
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: 12
                            color: "#18181b"
                            border.color: "#27272a"
                            implicitHeight: 74

                            Column {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 6

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
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            radius: 12
                            color: "#18181b"
                            border.color: "#27272a"
                            implicitHeight: 74

                            Column {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 6

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
                    }
                }

                Item {
                    Layout.fillHeight: true
                }

                Label {
                    Layout.fillWidth: true
                    text: "Business logic stays in Python, while the interface is now fully declarative and hardware-accelerated."
                    color: "#64748b"
                    wrapMode: Text.WordWrap
                    font.pixelSize: 12
                }
            }
        }

        Item {
            SplitView.fillWidth: true
            SplitView.minimumWidth: 680

            RowLayout {
                anchors.fill: parent
                anchors.margins: 24
                spacing: 20

                ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 620
                    clip: true

                    ColumnLayout {
                        width: parent.width
                        spacing: 18

                        SectionCard {
                            Layout.fillWidth: true
                            title: "Source"
                            subtitle: "Choose an existing YouTube subtitle track or transcribe a local media file before translation."

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 12

                                RadioButton {
                                    checked: appBridge.mode === "youtube"
                                    text: "YouTube URL"
                                    onClicked: appBridge.mode = "youtube"
                                }

                                RadioButton {
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

                            TextField {
                                visible: appBridge.mode === "youtube"
                                Layout.fillWidth: true
                                placeholderText: "https://youtube.com/watch?v=..."
                                text: appBridge.url
                                color: "#ffffff"
                                placeholderTextColor: "#71717a"
                                selectByMouse: true
                                onTextEdited: appBridge.url = text
                                background: Rectangle {
                                    radius: 12
                                    color: "#18181b"
                                    border.width: 1
                                    border.color: "#27272a"
                                }
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

                                TextField {
                                    Layout.fillWidth: true
                                    placeholderText: "Select a .mp4, .mkv, .wav, .mp3..."
                                    text: appBridge.filePath
                                    color: "#ffffff"
                                    placeholderTextColor: "#71717a"
                                    selectByMouse: true
                                    onTextEdited: appBridge.filePath = text
                                    background: Rectangle {
                                        radius: 12
                                        color: "#18181b"
                                        border.width: 1
                                        border.color: "#27272a"
                                    }
                                }

                                Button {
                                    text: "Browse"
                                    onClicked: inputFileDialog.open()
                                }
                            }
                        }

                        SectionCard {
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

                                TextField {
                                    Layout.fillWidth: true
                                    placeholderText: "Optional .srt output path"
                                    text: appBridge.outPath
                                    color: "#ffffff"
                                    placeholderTextColor: "#71717a"
                                    selectByMouse: true
                                    onTextEdited: appBridge.outPath = text
                                    background: Rectangle {
                                        radius: 12
                                        color: "#18181b"
                                        border.width: 1
                                        border.color: "#27272a"
                                    }
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

                            TextField {
                                Layout.fillWidth: true
                                placeholderText: "40"
                                text: appBridge.batch
                                color: "#ffffff"
                                validator: IntValidator { bottom: 1 }
                                onTextEdited: appBridge.batch = text
                                background: Rectangle {
                                    radius: 12
                                    color: "#18181b"
                                    border.width: 1
                                    border.color: "#27272a"
                                }
                            }
                        }

                        SectionCard {
                            Layout.fillWidth: true
                            title: "Translation Backend"
                            subtitle: "Use a hosted OpenAI-compatible endpoint or your own local llama.cpp server."

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 12

                                RadioButton {
                                    checked: appBridge.backend === "cloud"
                                    text: "Cloud API"
                                    onClicked: appBridge.backend = "cloud"
                                }

                                RadioButton {
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

                                TextField {
                                    Layout.fillWidth: true
                                    echoMode: TextInput.Password
                                    placeholderText: "OpenAI-compatible key"
                                    text: appBridge.apiKey
                                    color: "#ffffff"
                                    onTextEdited: appBridge.apiKey = text
                                    background: Rectangle {
                                        radius: 12
                                        color: "#18181b"
                                        border.width: 1
                                        border.color: "#27272a"
                                    }
                                }

                                Label {
                                    text: "Base URL"
                                    color: "#cbd5e1"
                                    font.pixelSize: 12
                                }

                                TextField {
                                    Layout.fillWidth: true
                                    placeholderText: "https://api.openai.com/v1"
                                    text: appBridge.baseUrl
                                    color: "#ffffff"
                                    selectByMouse: true
                                    onTextEdited: appBridge.baseUrl = text
                                    background: Rectangle {
                                        radius: 12
                                        color: "#18181b"
                                        border.width: 1
                                        border.color: "#27272a"
                                    }
                                }

                                Label {
                                    text: "Model"
                                    color: "#cbd5e1"
                                    font.pixelSize: 12
                                }

                                TextField {
                                    Layout.fillWidth: true
                                    placeholderText: "gpt-4o-mini"
                                    text: appBridge.model
                                    color: "#ffffff"
                                    selectByMouse: true
                                    onTextEdited: appBridge.model = text
                                    background: Rectangle {
                                        radius: 12
                                        color: "#18181b"
                                        border.width: 1
                                        border.color: "#27272a"
                                    }
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

                                        TextField {
                                            Layout.fillWidth: true
                                            text: appBridge.host
                                            color: "#ffffff"
                                            onTextEdited: appBridge.host = text
                                            background: Rectangle {
                                                radius: 12
                                                color: "#18181b"
                                                border.width: 1
                                                border.color: "#27272a"
                                            }
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true

                                        Label {
                                            text: "Port"
                                            color: "#cbd5e1"
                                            font.pixelSize: 12
                                        }

                                        TextField {
                                            Layout.fillWidth: true
                                            text: appBridge.port
                                            color: "#ffffff"
                                            validator: IntValidator { bottom: 1 }
                                            onTextEdited: appBridge.port = text
                                            background: Rectangle {
                                                radius: 12
                                                color: "#18181b"
                                                border.width: 1
                                                border.color: "#27272a"
                                            }
                                        }
                                    }
                                }

                                Label {
                                    text: "Model name"
                                    color: "#cbd5e1"
                                    font.pixelSize: 12
                                }

                                TextField {
                                    Layout.fillWidth: true
                                    text: appBridge.modelName
                                    color: "#ffffff"
                                    selectByMouse: true
                                    onTextEdited: appBridge.modelName = text
                                    background: Rectangle {
                                        radius: 12
                                        color: "#18181b"
                                        border.width: 1
                                        border.color: "#27272a"
                                    }
                                }
                            }
                        }

                        SectionCard {
                            visible: appBridge.mode === "file"
                            Layout.fillWidth: true
                            title: "Local ASR"
                            subtitle: "Fine-tune the SenseVoiceSmall runtime for local transcription. Leave paths blank to use PATH and ./gguf defaults."

                            Label {
                                text: "Spoken language"
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

                            Label {
                                text: "SenseVoice binary"
                                color: "#cbd5e1"
                                font.pixelSize: 12
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                TextField {
                                    Layout.fillWidth: true
                                    text: appBridge.asrBin
                                    color: "#ffffff"
                                    selectByMouse: true
                                    onTextEdited: appBridge.asrBin = text
                                    background: Rectangle {
                                        radius: 12
                                        color: "#18181b"
                                        border.width: 1
                                        border.color: "#27272a"
                                    }
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

                                TextField {
                                    Layout.fillWidth: true
                                    text: appBridge.asrVadBin
                                    color: "#ffffff"
                                    selectByMouse: true
                                    onTextEdited: appBridge.asrVadBin = text
                                    background: Rectangle {
                                        radius: 12
                                        color: "#18181b"
                                        border.width: 1
                                        border.color: "#27272a"
                                    }
                                }

                                Button {
                                    text: "Browse"
                                    onClicked: asrVadDialog.open()
                                }
                            }

                            Label {
                                text: "SenseVoice model (.gguf)"
                                color: "#cbd5e1"
                                font.pixelSize: 12
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                TextField {
                                    Layout.fillWidth: true
                                    text: appBridge.asrModel
                                    color: "#ffffff"
                                    selectByMouse: true
                                    onTextEdited: appBridge.asrModel = text
                                    background: Rectangle {
                                        radius: 12
                                        color: "#18181b"
                                        border.width: 1
                                        border.color: "#27272a"
                                    }
                                }

                                Button {
                                    text: "Browse"
                                    onClicked: asrModelDialog.open()
                                }
                            }

                            Label {
                                text: "VAD model (.gguf)"
                                color: "#cbd5e1"
                                font.pixelSize: 12
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                TextField {
                                    Layout.fillWidth: true
                                    text: appBridge.asrVadModel
                                    color: "#ffffff"
                                    selectByMouse: true
                                    onTextEdited: appBridge.asrVadModel = text
                                    background: Rectangle {
                                        radius: 12
                                        color: "#18181b"
                                        border.width: 1
                                        border.color: "#27272a"
                                    }
                                }

                                Button {
                                    text: "Browse"
                                    onClicked: asrVadModelDialog.open()
                                }
                            }
                        }
                    }
                }

                SectionCard {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 500
                    title: "Execution Log"
                    subtitle: "The CLI pipeline still runs unchanged, but its output now streams through the Qt bridge in real time."

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
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

    FileDialog {
        id: asrBinDialog
        title: "Select SenseVoice binary"
        onAccepted: appBridge.asrBin = appBridge.localPath(selectedFile.toString())
    }

    FileDialog {
        id: asrVadDialog
        title: "Select VAD binary"
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
}
