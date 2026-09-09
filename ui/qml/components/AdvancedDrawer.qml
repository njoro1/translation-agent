import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."

ColumnLayout {
    id: root

    property bool expanded: false
    property bool segExpanded: false

    spacing: Theme.sm

    readonly property bool isLocalMode: appBridge.pipelineMode !== "youtube_cloud"
    readonly property bool isCloudMode: appBridge.pipelineMode !== "offline"

    // Toggle row
    Rectangle {
        Layout.fillWidth: true
        implicitHeight: 32
        radius: Theme.radiusSm
        color: toggleMouse.containsMouse ? Theme.surfaceAlt : Theme.surface
        border.color: Theme.border

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.sm
            anchors.rightMargin: Theme.sm

            Label {
                text: root.expanded ? "\u25BC" : "\u25B6"
                color: Theme.textMuted
                font.pixelSize: Theme.fontSmall
            }

            FieldLabel {
                text: "ADVANCED SETTINGS"
            }

            Item { Layout.fillWidth: true }
        }

        MouseArea {
            id: toggleMouse
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            hoverEnabled: true
            onClicked: root.expanded = !root.expanded
        }
    }

        ColumnLayout {
            visible: root.expanded
            Layout.fillWidth: true
            spacing: Theme.sm

            // --- Appearance ------------------------------------------------------
            Switch {
                checked: appBridge.comfortable
                onToggled: appBridge.setComfortable(checked)
                text: "Comfortable density (larger hit targets)"
                font.pixelSize: Theme.fontSmall
                Accessible.name: "Comfortable density"

                indicator: Rectangle {
                    implicitWidth: 30
                    implicitHeight: 16
                    radius: 8
                    color: parent.checked ? Theme.accent : Theme.border

                    Rectangle {
                        x: parent.checked ? parent.width - width - 2 : 2
                        anchors.verticalCenter: parent.verticalCenter
                        width: 12
                        height: 12
                        radius: 6
                        color: "#FFFFFF"

                        Behavior on x { NumberAnimation { duration: 120 } }
                    }
                }

                contentItem: Label {
                    text: parent.text
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: parent.indicator.width + 6
                }
            }

            Switch {
                checked: appBridge.reducedMotion
                onToggled: appBridge.setReducedMotion(checked)
                text: "Reduce motion (fewer animations)"
                font.pixelSize: Theme.fontSmall
                Accessible.name: "Reduce motion"

                indicator: Rectangle {
                    implicitWidth: 30
                    implicitHeight: 16
                    radius: 8
                    color: parent.checked ? Theme.accent : Theme.border

                    Rectangle {
                        x: parent.checked ? parent.width - width - 2 : 2
                        anchors.verticalCenter: parent.verticalCenter
                        width: 12
                        height: 12
                        radius: 6
                        color: "#FFFFFF"

                        Behavior on x { NumberAnimation { duration: 120 } }
                    }
                }

                contentItem: Label {
                    text: parent.text
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                    verticalAlignment: Text.AlignVCenter
                    leftPadding: parent.indicator.width + 6
                }
            }

        // --- Batch / context -------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.sm

            FieldLabel { text: "Batch size"; Layout.preferredWidth: 120 }
            CompactTextField {
                Layout.fillWidth: true
                text: appBridge.batch
                onEditingFinished: appBridge.batch = text
                validator: IntValidator { bottom: 1; top: 64 }
                ToolTip.visible: hovered
                ToolTip.delay: 500
                ToolTip.text: "Cues per translation window (4-16 recommended)."
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.sm

            FieldLabel { text: "Context mode"; Layout.preferredWidth: 120 }
            CompactComboBox {
                Layout.fillWidth: true
                textRole: "label"
                valueRole: "id"
                model: [
                    { id: "", label: "Preset default" },
                    { id: "off", label: "Off" },
                    { id: "light", label: "Light" },
                    { id: "standard", label: "Standard" },
                    { id: "deep", label: "Deep" }
                ]
                currentIndex: {
                    for (let i = 0; i < model.length; i++) {
                        if (model[i].id === appBridge.contextMode) return i
                    }
                    return 0
                }
                onActivated: appBridge.contextMode = currentValue
                ToolTip.visible: hovered
                ToolTip.delay: 500
                ToolTip.text: "How much surrounding context each translation window carries."
            }
        }

        Switch {
            checked: appBridge.contextSummary
            onToggled: appBridge.contextSummary = checked
            text: "Rolling scene summary (cloud, experimental)"
            font.pixelSize: Theme.fontSmall

            indicator: Rectangle {
                implicitWidth: 30
                implicitHeight: 16
                radius: 8
                color: parent.checked ? Theme.accent : Theme.border

                Rectangle {
                    x: parent.checked ? parent.width - width - 2 : 2
                    anchors.verticalCenter: parent.verticalCenter
                    width: 12
                    height: 12
                    radius: 6
                    color: "#FFFFFF"

                    Behavior on x { NumberAnimation { duration: 120 } }
                }
            }

            contentItem: Label {
                text: parent.text
                color: Theme.textMuted
                font.pixelSize: Theme.fontSmall
                verticalAlignment: Text.AlignVCenter
                leftPadding: parent.indicator.width + 6
            }
        }

        // --- Preprocessing (local modes) --------------------------------------
        RowLayout {
            visible: root.isLocalMode
            Layout.fillWidth: true
            spacing: Theme.sm

            FieldLabel { text: "Preprocess"; Layout.preferredWidth: 120 }
            CompactComboBox {
                Layout.fillWidth: true
                textRole: "label"
                valueRole: "id"
                model: [
                    { id: "auto", label: "Auto (preset)" },
                    { id: "none", label: "None" },
                    { id: "basic", label: "Basic (high-pass)" },
                    { id: "loudnorm", label: "Loudness norm" },
                    { id: "denoise", label: "Denoise" }
                ]
                currentIndex: {
                    for (let i = 0; i < model.length; i++) {
                        if (model[i].id === appBridge.asrPreprocess) return i
                    }
                    return 0
                }
                onActivated: appBridge.asrPreprocess = currentValue
                ToolTip.visible: hovered
                ToolTip.delay: 500
                ToolTip.text: "FFmpeg audio conditioning before ASR. Duration-safe with automatic fallback."
            }
        }

        // --- ASR segmentation tuning (local modes, advanced) ------------------
        ColumnLayout {
            visible: root.isLocalMode
            Layout.fillWidth: true
            spacing: Theme.xs

            // Collapsed sub-group: these are expert knobs most users never touch.
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 30
                radius: Theme.radiusSm
                color: segMouse.containsMouse ? Theme.surfaceAlt : Theme.surface
                border.color: Theme.border

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.sm
                    anchors.rightMargin: Theme.sm

                    Label {
                        text: root.segExpanded ? "\u25BC" : "\u25B6"
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                    }
                    FieldLabel { text: "Segmentation (advanced)" }
                    Item { Layout.fillWidth: true }
                }

                MouseArea {
                    id: segMouse
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    hoverEnabled: true
                    onClicked: root.segExpanded = !root.segExpanded
                }

                Accessible.role: Accessible.Button
                Accessible.name: "Segmentation advanced settings, " + (root.segExpanded ? "expanded" : "collapsed")
            }

            GridLayout {
                visible: root.segExpanded
                Layout.fillWidth: true
                columns: 2
                columnSpacing: Theme.sm
                rowSpacing: Theme.xs

                // Declarative bindings (no Component.onCompleted): the fields stay
                // in sync if a preset or config load changes the bridge values.
                FieldLabel { text: "Max segment ms" }
                CompactTextField {
                    Layout.fillWidth: true
                    text: appBridge.asrMaxSegmentMs
                    validator: IntValidator { bottom: 500 }
                    onEditingFinished: appBridge.asrMaxSegmentMs = text
                    ToolTip.visible: hovered
                    ToolTip.delay: 500
                    ToolTip.text: "Longest audio chunk sent to ASR at once. Lower = more, shorter cues but slower."
                }

                FieldLabel { text: "End silence ms" }
                CompactTextField {
                    Layout.fillWidth: true
                    text: appBridge.asrMaxEndSilenceMs
                    validator: IntValidator { bottom: 50 }
                    onEditingFinished: appBridge.asrMaxEndSilenceMs = text
                    ToolTip.visible: hovered
                    ToolTip.delay: 500
                    ToolTip.text: "Trailing silence (ms) allowed before a segment is considered finished."
                }

                FieldLabel { text: "Speech/noise thres" }
                CompactTextField {
                    Layout.fillWidth: true
                    text: appBridge.asrSpeechNoiseThreshold
                    validator: DoubleValidator { bottom: 0.0; top: 1.0 }
                    onEditingFinished: appBridge.asrSpeechNoiseThreshold = text
                    ToolTip.visible: hovered
                    ToolTip.delay: 500
                    ToolTip.text: "Silero VAD probability (0–1) above which a frame counts as speech."
                }

                FieldLabel { text: "Noise dB" }
                CompactTextField {
                    Layout.fillWidth: true
                    text: appBridge.asrNoiseDb
                    onEditingFinished: appBridge.asrNoiseDb = text
                    ToolTip.visible: hovered
                    ToolTip.delay: 500
                    ToolTip.text: "Audio quieter than this dB is filtered out before voice detection."
                }

                FieldLabel { text: "Min silence s" }
                CompactTextField {
                    Layout.fillWidth: true
                    text: appBridge.asrMinSilenceS
                    validator: DoubleValidator { bottom: 0.05 }
                    onEditingFinished: appBridge.asrMinSilenceS = text
                    ToolTip.visible: hovered
                    ToolTip.delay: 500
                    ToolTip.text: "Shortest silence (seconds) that splits one subtitle cue from the next."
                }

                FieldLabel { text: "Max cue duration ms" }
                CompactTextField {
                    Layout.fillWidth: true
                    text: appBridge.asrMaxCueDurationMs
                    validator: IntValidator { bottom: 500 }
                    onEditingFinished: appBridge.asrMaxCueDurationMs = text
                    ToolTip.visible: hovered
                    ToolTip.delay: 500
                    ToolTip.text: "If a single cue runs longer than this, the speech is split into two cues."
                }

                FieldLabel { text: "Max cue chars" }
                CompactTextField {
                    Layout.fillWidth: true
                    text: appBridge.asrMaxCueChars
                    validator: IntValidator { bottom: 10 }
                    onEditingFinished: appBridge.asrMaxCueChars = text
                    ToolTip.visible: hovered
                    ToolTip.delay: 500
                    ToolTip.text: "Hard cap on Latin characters per cue (forces a split when exceeded)."
                }

                FieldLabel { text: "Max CJK chars" }
                CompactTextField {
                    Layout.fillWidth: true
                    text: appBridge.asrMaxCueCharsCjk
                    validator: IntValidator { bottom: 5 }
                    onEditingFinished: appBridge.asrMaxCueCharsCjk = text
                    ToolTip.visible: hovered
                    ToolTip.delay: 500
                    ToolTip.text: "Hard cap on CJK characters per cue (forces a split when exceeded)."
                }
            }
        }

        // --- Translation memory -----------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.sm

            FieldLabel { text: "Memory mode"; Layout.preferredWidth: 120 }
            CompactComboBox {
                Layout.fillWidth: true
                textRole: "label"
                valueRole: "id"
                model: [
                    { id: "auto", label: "Auto" },
                    { id: "on", label: "On" },
                    { id: "off", label: "Off" }
                ]
                currentIndex: {
                    for (let i = 0; i < model.length; i++) {
                        if (model[i].id === appBridge.translationMemoryMode) return i
                    }
                    return 0
                }
                onActivated: appBridge.translationMemoryMode = currentValue
            }
        }

        // --- Glossary ----------------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.sm

            FieldLabel { text: "Glossary"; Layout.preferredWidth: 120 }
            CompactTextField {
                id: glossaryField
                Layout.fillWidth: true
                text: appBridge.glossaryPath
                placeholderText: "Optional .txt glossary"
                onEditingFinished: appBridge.glossaryPath = appBridge.localPath(text)
            }
            Button {
                text: "…"
                implicitWidth: 30
                onClicked: glossaryDialog.open()

                background: Rectangle {
                    color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                    radius: Theme.radiusSm
                    border.color: Theme.border
                }
                contentItem: Label { text: "…"; color: Theme.text; horizontalAlignment: Text.AlignHCenter }
            }
        }

        FileDialog {
            id: glossaryDialog
            nameFilters: ["Text files (*.txt *.csv *.tsv)", "All files (*)"]
            onAccepted: {
                glossaryField.text = appBridge.localPath(selectedFile)
                appBridge.glossaryPath = appBridge.localPath(selectedFile)
            }
        }

        // --- Strict quality ------------------------------------------------------
        Switch {
            checked: appBridge.strictQuality
            onToggled: appBridge.strictQuality = checked
            text: "Strict quality (fail on serious errors)"
            font.pixelSize: Theme.fontSmall

            indicator: Rectangle {
                implicitWidth: 30
                implicitHeight: 16
                radius: 8
                color: parent.checked ? Theme.accent : Theme.border

                Rectangle {
                    x: parent.checked ? parent.width - width - 2 : 2
                    anchors.verticalCenter: parent.verticalCenter
                    width: 12
                    height: 12
                    radius: 6
                    color: "#FFFFFF"

                    Behavior on x { NumberAnimation { duration: 120 } }
                }
            }

            contentItem: Label {
                text: parent.text
                color: Theme.textMuted
                font.pixelSize: Theme.fontSmall
                verticalAlignment: Text.AlignVCenter
                leftPadding: parent.indicator.width + 6
            }
        }

        // --- Cloud credentials (cloud modes) ------------------------------------
        ColumnLayout {
            visible: root.isCloudMode
            Layout.fillWidth: true
            spacing: Theme.xs

            FieldLabel { text: "CLOUD API (BLANK = USE .ENV)" }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.sm

                FieldLabel { text: "API key"; Layout.preferredWidth: 120 }
                CompactTextField {
                    Layout.fillWidth: true
                    echoMode: TextInput.Password
                    text: appBridge.apiKey
                    placeholderText: "sk-…"
                    onEditingFinished: appBridge.apiKey = text
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.sm

                FieldLabel { text: "Base URL"; Layout.preferredWidth: 120 }
                CompactTextField {
                    Layout.fillWidth: true
                    text: appBridge.baseUrl
                    placeholderText: "https://api.openai.com/v1"
                    onEditingFinished: appBridge.baseUrl = text
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.sm

                FieldLabel { text: "Model"; Layout.preferredWidth: 120 }
                CompactTextField {
                    Layout.fillWidth: true
                    text: appBridge.model
                    placeholderText: "gpt-4o-mini"
                    onEditingFinished: appBridge.model = text
                }
            }
        }

        // --- Local translation model (offline) ----------------------------------
        ColumnLayout {
            visible: !root.isCloudMode
            Layout.fillWidth: true
            spacing: Theme.xs

            FieldLabel { text: "LOCAL TRANSLATION MODEL" }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.sm

                Label {
                    text: appBridge.localModelReady ? "\u2713 Model ready" : "! No local model"
                    color: appBridge.localModelReady ? Theme.success : Theme.warning
                    font.pixelSize: Theme.fontSmall
                }

                Item { Layout.fillWidth: true }

                Button {
                    visible: !appBridge.localModelReady
                    text: appBridge.localModelDownloading ? "Downloading…" : "Download Hy-MT2"
                    enabled: !appBridge.localModelDownloading
                    onClicked: appBridge.downloadLocalModel()

                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: parent.enabled ? (parent.hovered ? Theme.accentHover : Theme.accent) : Theme.surfaceAlt
                    }
                    contentItem: Label {
                        text: parent.text
                        color: parent.enabled ? "#FFFFFF" : Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.sm

                FieldLabel { text: "GGUF path"; Layout.preferredWidth: 120 }
                CompactTextField {
                    id: localModelField
                    Layout.fillWidth: true
                    text: appBridge.localModel
                    placeholderText: "Auto-detected in ./gguf"
                    onEditingFinished: appBridge.localModel = appBridge.localPath(text)
                }
                Button {
                    text: "…"
                    implicitWidth: 30
                    onClicked: localModelDialog.open()

                    background: Rectangle {
                        color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                        radius: Theme.radiusSm
                        border.color: Theme.border
                    }
                    contentItem: Label { text: "…"; color: Theme.text; horizontalAlignment: Text.AlignHCenter }
                }
            }

            FileDialog {
                id: localModelDialog
                nameFilters: ["GGUF models (*.gguf)", "All files (*)"]
                onAccepted: {
                    localModelField.text = appBridge.localPath(selectedFile)
                    appBridge.localModel = appBridge.localPath(selectedFile)
                }
            }
        }
    }
}
