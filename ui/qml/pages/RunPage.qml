import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."
import "../components"

// Run screen: Source → Pipeline → Inspector, full height, no dead space.
Item {
    id: root

    readonly property bool isYouTubeMode: appBridge.pipelineMode === "youtube_cloud"
    readonly property bool isOfflineMode: appBridge.pipelineMode === "offline"
    readonly property bool isLocalMode: appBridge.pipelineMode !== "youtube_cloud"
    readonly property bool hasResult: appBridge.resultReady

    readonly property var readiness: appBridge.readinessRows
    readonly property int readyOk: {
        var n = 0
        for (var i = 0; i < readiness.length; i++)
            if (readiness[i].state === "ok") n++
        return n
    }
    readonly property int readyRequired: {
        var n = 0
        for (var i = 0; i < readiness.length; i++)
            if (readiness[i].state !== "n/a") n++
        return n
    }

    signal navigateRequested(int page)
    signal openSettingsRequested(string section)

    // =====================================================================
    RowLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16

        // -------------------------------------------------------- SOURCE --
        ScrollView {
            Layout.preferredWidth: 364
            Layout.minimumWidth: 300
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            AppCard {
                id: sourceCard
                width: 364 - 10
                title: "Source"
                stepNumber: 1
                active: !root.isYouTubeMode || appBridge.url !== ""
                headerExtra: [
                    Chip {
                        text: root.isYouTubeMode ? "YouTube" : "Local file"
                        tone: "acc"
                    }
                ]

                ColumnLayout {
                    width: parent.width
                    spacing: 10

                    // --- YouTube URL ---------------------------------------
                    ColumnLayout {
                        visible: root.isYouTubeMode
                        Layout.fillWidth: true
                        spacing: 8

                        CompactTextField {
                            id: urlField
                            Layout.fillWidth: true
                            label: "YouTube URL"
                            text: appBridge.url
                            placeholderText: "https://www.youtube.com/watch?v=…"
                            onEditingFinished: appBridge.url = text
                            onTextEdited: {
                                appBridge.url = text
                                urlAutoParseTimer.restart()
                            }

                            // Auto-parse: once the URL stops changing (covers
                            // paste + typing), inspect the formats automatically.
                            Timer {
                                id: urlAutoParseTimer
                                interval: 800
                                repeat: false
                                onTriggered: {
                                    if (root.isYouTubeMode && urlField.text.trim() !== ""
                                            && !appBridge.youtubeInfoLoading
                                            && !appBridge.youtubeDownloading)
                                        appBridge.fetchYouTubeInfo()
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            AppButton {
                                text: appBridge.youtubeInfoLoading ? "Inspecting…" : "Inspect"
                                small: true
                                variant: "primary"
                                iconName: "search"
                                enabled: !appBridge.youtubeInfoLoading && appBridge.url.trim() !== ""
                                onClicked: appBridge.fetchYouTubeInfo()
                            }

                            AppButton {
                                text: "Clear"
                                small: true
                                variant: "ghost"
                                iconName: "x"
                                visible: appBridge.url !== ""
                                onClicked: appBridge.url = ""
                            }

                            Item { Layout.fillWidth: true }
                        }

                        // Preview tile: what the pipeline is about to work on.
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 74
                            radius: Theme.radiusMd
                            color: Theme.surfaceRaised
                            border.color: Theme.border
                            border.width: 1

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 12

                                Rectangle {
                                    implicitWidth: 50
                                    implicitHeight: 50
                                    radius: Theme.radiusSm
                                    color: Theme.inset

                                    Icon {
                                        anchors.centerIn: parent
                                        name: "film"
                                        width: 22
                                        height: 22
                                        color: appBridge.youtubeHasInfo ? Theme.accent : Theme.textMuted
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 3

                                    Label {
                                        Layout.fillWidth: true
                                        text: appBridge.youtubeTitle !== ""
                                              ? appBridge.youtubeTitle
                                              : (appBridge.url !== ""
                                                 ? "Not inspected yet"
                                                 : "Paste a YouTube URL")
                                        color: appBridge.youtubeTitle !== "" ? Theme.text : Theme.textMuted
                                        font.pixelSize: Theme.fontBody
                                        font.bold: true
                                        wrapMode: Text.WordWrap
                                        maximumLineCount: 2
                                        elide: Text.ElideRight
                                    }

                                    RowLayout {
                                        spacing: 6

                                        Chip {
                                            visible: appBridge.youtubeHasInfo
                                            text: appBridge.youtubeSelectedFormatLabel !== ""
                                                  ? appBridge.youtubeSelectedFormatLabel
                                                  : "Best available"
                                            mono: true
                                        }
                                        Chip {
                                            visible: appBridge.youtubeHasInfo
                                            text: appBridge.youtubeHasEnglishSubtitle
                                                  ? "English track" : "No English track"
                                            tone: appBridge.youtubeHasEnglishSubtitle ? "ok" : "warn"
                                            iconName: appBridge.youtubeHasEnglishSubtitle ? "check" : "alert"
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // --- Local file ----------------------------------------
                    ColumnLayout {
                        visible: !root.isYouTubeMode
                        Layout.fillWidth: true
                        spacing: 8

                        Rectangle {
                            id: dropZone
                            Layout.fillWidth: true
                            implicitHeight: 84
                            radius: Theme.radiusMd
                            color: Theme.inset
                            border.width: 1.5
                            border.color: dropArea.containsDrag ? Theme.accent : Theme.borderStrong

                            DropArea {
                                id: dropArea
                                anchors.fill: parent
                                onDropped: (drop) => {
                                    if (drop.hasUrls && drop.urls.length > 0)
                                        appBridge.filePath = appBridge.localPath(drop.urls[0])
                                }
                            }

                            ColumnLayout {
                                anchors.centerIn: parent
                                spacing: 4

                                Icon {
                                    Layout.alignment: Qt.AlignHCenter
                                    name: "upload"
                                    width: 24
                                    height: 24
                                    color: Theme.textMuted
                                }

                                Label {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: "Drop media here"
                                    color: Theme.textDim
                                    font.pixelSize: Theme.fontBody
                                    font.bold: true
                                }

                                AppButton {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: "Browse"
                                    small: true
                                    iconName: "folder"
                                    onClicked: inputFileMenu.open()
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Icon { name: "file"; width: 15; height: 15; color: Theme.textMuted }

                            Label {
                                Layout.fillWidth: true
                                text: appBridge.filePath !== ""
                                      ? appBridge.filePath.split(/[\\/]/).pop()
                                      : "No file selected"
                                color: appBridge.filePath !== "" ? Theme.text : Theme.textMuted
                                font.pixelSize: Theme.fontSmall
                                elide: Text.ElideMiddle
                            }

                            Chip {
                                visible: appBridge.filePath !== ""
                                text: appBridge.fileSizeText
                                mono: true
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Label {
                                text: "Spoken"
                                Layout.preferredWidth: 66
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSmall
                            }
                            CompactComboBox {
                                Layout.fillWidth: true
                                label: "Spoken language"
                                editable: true
                                editText: appBridge.asrLanguage
                                model: ["auto", "ja", "zh", "zh-TW", "ko", "yue", "en"]
                                onAccepted: appBridge.asrLanguage = editText.trim()
                                onActivated: appBridge.asrLanguage = editText.trim()
                                ToolTip.visible: hovered
                                ToolTip.delay: 500
                                ToolTip.text: "Spoken language the ASR transcribes (auto = detect)."
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Label {
                                text: "Translate from"
                                Layout.preferredWidth: 66
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSmall
                            }
                            CompactComboBox {
                                Layout.fillWidth: true
                                label: "Translation source language override"
                                editable: true
                                editText: appBridge.sourceLang
                                model: ["", "ja", "zh", "zh-TW", "ko", "yue", "en"]
                                onAccepted: appBridge.sourceLang = editText.trim()
                                onActivated: appBridge.sourceLang = editText.trim()
                                ToolTip.visible: hovered
                                ToolTip.delay: 500
                                ToolTip.text: "Override the translation source language. Blank = use the spoken (ASR) language."
                            }
                        }
                    }

                    // --- Subtitle source (YouTube) --------------------------
                    Rectangle {
                        visible: root.isYouTubeMode
                        Layout.fillWidth: true
                        implicitHeight: 1
                        color: Theme.borderSoft
                    }

                    ColumnLayout {
                        visible: root.isYouTubeMode
                        Layout.fillWidth: true
                        spacing: 8

                        Label {
                            text: "SUBTITLE"
                            color: Theme.textMuted
                            font.pixelSize: 10
                            font.bold: true
                            font.letterSpacing: 0.8
                        }

                        YouTubeSubtitlePanel {
                            Layout.fillWidth: true
                        }
                    }

                    // --- Optional video download (YouTube) -------------------
                    Rectangle {
                        visible: root.isYouTubeMode
                        Layout.fillWidth: true
                        implicitHeight: 1
                        color: Theme.borderSoft
                    }

                    Item {
                        visible: root.isYouTubeMode
                        Layout.fillWidth: true
                        implicitHeight: 28

                        RowLayout {
                            anchors.fill: parent
                            spacing: 8

                            Icon {
                                name: videoSection.expanded ? "chevron" : "arrow"
                                width: 14
                                height: 14
                                color: Theme.textMuted
                            }
                            Label {
                                text: "VIDEO DOWNLOAD (OPTIONAL)"
                                color: Theme.textMuted
                                font.pixelSize: 10
                                font.bold: true
                                font.letterSpacing: 0.8
                            }
                            Item { Layout.fillWidth: true }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: videoSection.expanded = !videoSection.expanded
                        }
                    }

                    ColumnLayout {
                        id: videoSection
                        property bool expanded: false
                        visible: root.isYouTubeMode && expanded
                        Layout.fillWidth: true
                        spacing: 8

                        YouTubeVideoPanel {
                            Layout.fillWidth: true
                        }
                    }
                }
            }
        }

        // ------------------------------------------------------ PIPELINE --
        ScrollView {
            Layout.fillWidth: true
            Layout.minimumWidth: 320
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            AppCard {
                width: Math.max(300, pipelineArea.width - 10)
                title: "Pipeline"
                stepNumber: 2
                active: root.readyOk === root.readyRequired && root.readyRequired > 0

                property real pipelineArea: 0

                ColumnLayout {
                    width: parent.width
                    spacing: 14

                    // --- Output --------------------------------------------
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 9

                        Label {
                            text: "OUTPUT"
                            color: Theme.textMuted
                            font.pixelSize: 10
                            font.bold: true
                            font.letterSpacing: 0.8
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Label { text: "Path"; Layout.preferredWidth: 66; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            CompactTextField {
                                id: outPathField
                                Layout.fillWidth: true
                                text: appBridge.outPath
                                placeholderText: "Auto-named from the title"
                                label: "Output file path"
                                onEditingFinished: appBridge.outPath = appBridge.localPath(text)
                            }
                            AppButton {
                                text: "Choose"
                                small: true
                                variant: "ghost"
                                iconName: "folder"
                                onClicked: outputFileMenu.open()
                                Accessible.name: "Choose the output file"
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Label { text: "Format"; Layout.preferredWidth: 66; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            CompactComboBox {
                                Layout.preferredWidth: 110
                                label: "Output format"
                                model: ["srt", "ass"]
                                currentIndex: appBridge.outputFormat === "ass" ? 1 : 0
                                onActivated: appBridge.outputFormat = currentText
                            }

                            Item { Layout.fillWidth: true }

                            AppButton {
                                visible: appBridge.canOpenOutputFolder
                                text: "Open folder"
                                small: true
                                variant: "ghost"
                                iconName: "external"
                                onClicked: appBridge.openOutputFolder()
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

                    // --- Translation ----------------------------------------
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 9

                        Label {
                            text: "TRANSLATION"
                            color: Theme.textMuted
                            font.pixelSize: 10
                            font.bold: true
                            font.letterSpacing: 0.8
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 40
                            radius: Theme.radiusSm
                            color: Theme.surfaceAlt
                            border.color: Theme.borderSoft
                            border.width: 1

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 11
                                anchors.rightMargin: 11
                                spacing: 8

                                Pill {
                                    tone: root.isOfflineMode ? "acc" : "info"
                                    text: root.isOfflineMode ? "Local llama.cpp" : "Cloud LLM"
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: root.isOfflineMode
                                          ? appBridge.modelName
                                          : (appBridge.model !== "" ? appBridge.model : "model from .env")
                                    color: Theme.textDim
                                    font.pixelSize: Theme.fontSmall
                                    font.family: Theme.monoFont
                                    elide: Text.ElideRight
                                }

                                Chip {
                                    visible: !root.isOfflineMode
                                    text: appBridge.apiKey !== "" ? "custom key" : ".env"
                                    mono: true
                                }
                            }
                        }

                        // Local translation model state + download.
                        RowLayout {
                            visible: root.isOfflineMode
                            Layout.fillWidth: true
                            spacing: 8

                            Icon {
                                name: appBridge.localModelReady ? "check" : "alert"
                                width: 14
                                height: 14
                                color: appBridge.localModelReady ? Theme.success : Theme.warning
                            }
                            Label {
                                Layout.fillWidth: true
                                text: appBridge.localModelReady
                                      ? "Hy-MT2 translation model ready"
                                      : "No local translation model"
                                color: appBridge.localModelReady ? Theme.textDim : Theme.warning
                                font.pixelSize: Theme.fontSmall
                            }
                            AppButton {
                                visible: !appBridge.localModelReady
                                text: appBridge.localModelDownloading ? "Downloading…" : "Download"
                                small: true
                                variant: "primary"
                                iconName: "download"
                                enabled: !appBridge.localModelDownloading
                                onClicked: appBridge.downloadLocalModel()
                            }
                        }

                        // ASR model state + download (local modes).
                        RowLayout {
                            visible: root.isLocalMode && !appBridge.asrModelReady
                            Layout.fillWidth: true
                            spacing: 8

                            Icon { name: "alert"; width: 14; height: 14; color: Theme.warning }
                            Label {
                                Layout.fillWidth: true
                                text: "ASR model missing"
                                color: Theme.warning
                                font.pixelSize: Theme.fontSmall
                            }
                            AppButton {
                                text: appBridge.modelDownloading ? "Downloading…" : "Download ASR models"
                                small: true
                                variant: "primary"
                                iconName: "download"
                                enabled: !appBridge.modelDownloading
                                onClicked: appBridge.downloadAsrModels()
                            }
                        }

                        RowLayout {
                            visible: root.isLocalMode && appBridge.asrModelReady
                            Layout.fillWidth: true
                            spacing: 8

                            Icon { name: "check"; width: 14; height: 14; color: Theme.success }
                            Label {
                                Layout.fillWidth: true
                                text: "ASR model ready (SenseVoice + VAD)"
                                color: Theme.textDim
                                font.pixelSize: Theme.fontSmall
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Label { text: "Context"; Layout.preferredWidth: 66; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            CompactComboBox {
                                Layout.fillWidth: true
                                label: "Context mode"
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
                                    for (let i = 0; i < model.length; i++)
                                        if (model[i].id === appBridge.contextMode) return i
                                    return 0
                                }
                                onActivated: appBridge.contextMode = currentValue
                                ToolTip.visible: hovered
                                ToolTip.delay: 500
                                ToolTip.text: "How much surrounding context each translation window carries."
                            }

                            Label { text: "Batch"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            CompactTextField {
                                Layout.preferredWidth: 70
                                text: appBridge.batch
                                label: "Batch size"
                                validator: IntValidator { bottom: 1; top: 64 }
                                onEditingFinished: appBridge.batch = text
                                ToolTip.visible: hovered
                                ToolTip.delay: 500
                                ToolTip.text: "Cues per translation window (4-16 recommended)."
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Label { text: "Memory"; Layout.preferredWidth: 66; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            CompactComboBox {
                                Layout.preferredWidth: 130
                                label: "Translation memory"
                                textRole: "label"
                                valueRole: "id"
                                model: [
                                    { id: "auto", label: "Auto" },
                                    { id: "on", label: "On" },
                                    { id: "off", label: "Off" }
                                ]
                                currentIndex: {
                                    for (let i = 0; i < model.length; i++)
                                        if (model[i].id === appBridge.translationMemoryMode) return i
                                    return 0
                                }
                                onActivated: appBridge.translationMemoryMode = currentValue
                            }

                            Label { text: "Glossary"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            CompactTextField {
                                id: glossaryField
                                Layout.fillWidth: true
                                text: appBridge.glossaryPath
                                placeholderText: "Optional .txt glossary"
                                label: "Glossary file"
                                onEditingFinished: appBridge.glossaryPath = appBridge.localPath(text)
                            }
                            AppButton {
                                text: "Choose glossary"
                                small: true
                                variant: "ghost"
                                iconName: "folder"
                                onClicked: glossaryDialog.open()
                                Accessible.name: "Choose the glossary file"
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            AppSwitch {
                                text: "Strict quality gate (errors fail the run)"
                                checked: appBridge.strictQuality
                                onToggled: appBridge.strictQuality = checked
                            }

                            Item { Layout.fillWidth: true }

                            AppSwitch {
                                text: "Rolling scene summary"
                                checked: appBridge.contextSummary
                                onToggled: appBridge.contextSummary = checked
                                accessibleName: "Rolling scene summary (cloud, experimental)"
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

                    // --- Content preset -------------------------------------
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 9

                        Label {
                            text: "CONTENT PRESET"
                            color: Theme.textMuted
                            font.pixelSize: 10
                            font.bold: true
                            font.letterSpacing: 0.8
                        }

                        PresetPicker {
                            Layout.fillWidth: true
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: 6

                            Repeater {
                                model: ["auto", "anime", "drama", "music", "documentary", "variety", "lecture"]

                                delegate: Chip {
                                    required property var modelData
                                    text: modelData
                                    tone: appBridge.contentPreset === modelData ? "acc" : ""

                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: appBridge.contentPreset = modelData
                                    }
                                }
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

                    // --- Advanced pointer -----------------------------------
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Label {
                            Layout.fillWidth: true
                            text: "ASR segmentation, cloud credentials, API keys and model paths live in Settings."
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSmall
                            wrapMode: Text.WordWrap
                        }

                        AppButton {
                            text: "Open Settings"
                            small: true
                            iconName: "settings"
                            onClicked: root.openSettingsRequested("translation")
                        }
                    }
                }
            }
        }

        // ----------------------------------------------------- INSPECTOR --
        ScrollView {
            Layout.preferredWidth: 332
            Layout.minimumWidth: 300
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: 332 - 10
                spacing: 16

                AppCard {
                    Layout.fillWidth: true
                    title: "Readiness"
                    stepNumber: 3
                    active: root.readyOk === root.readyRequired && root.readyRequired > 0
                    headerExtra: [
                        Pill {
                            tone: root.readyOk === root.readyRequired ? "ok" : "warn"
                            text: root.readyOk + " / " + root.readyRequired
                        }
                    ]

                    ReadinessChecklist {
                        Layout.fillWidth: true
                    }
                }

                ErrorCard {
                    id: errorCard
                }

                AppCard {
                    Layout.fillWidth: true
                    visible: appBridge.isRunning || appBridge.statusState === "done"
                             || appBridge.statusState === "failed"
                             || appBridge.statusState === "cancelled"
                    title: appBridge.isRunning ? "Live run" : "Progress"

                    ProgressPanel {
                        Layout.fillWidth: true
                    }
                }

                AppCard {
                    Layout.fillWidth: true
                    visible: appBridge.resultReady
                    title: "Last run"
                    headerExtra: [
                        Chip {
                            text: appBridge.outputPathResolved.split(/[\\/]/).pop()
                            mono: true
                        }
                    ]

                    ColumnLayout {
                        width: parent.width
                        spacing: 10

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Icon {
                                name: appBridge.resultStrictState === "fail" ? "x" : "check"
                                width: 15
                                height: 15
                                color: appBridge.resultStrictState === "fail" ? Theme.error : Theme.success
                            }
                            Label {
                                Layout.fillWidth: true
                                text: appBridge.outputPathResolved
                                color: Theme.text
                                font.pixelSize: Theme.fontSmall
                                elide: Text.ElideMiddle
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            StatTile { value: String(appBridge.qualityTotalCues); label: "Cues" }
                            StatTile {
                                value: String(appBridge.qualityUntranslated)
                                label: "Failed"
                                tone: appBridge.qualityUntranslated > 0 ? "err" : "ok"
                            }
                            StatTile {
                                value: String(appBridge.qualityWarnings)
                                label: "Warn"
                                tone: appBridge.qualityWarnings > 0 ? "warn" : "ok"
                            }
                            StatTile {
                                value: appBridge.resultStrictState === "pass" ? "PASS"
                                       : appBridge.resultStrictState === "fail" ? "FAIL" : "OFF"
                                label: "Gate"
                                tone: appBridge.resultStrictState === "fail" ? "err"
                                      : appBridge.resultStrictState === "pass" ? "ok" : "mute"
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            AppButton {
                                text: "Open Review"
                                small: true
                                variant: "primary"
                                iconName: "list"
                                onClicked: root.navigateRequested(1)
                            }
                            AppButton {
                                text: "Open Quality"
                                small: true
                                iconName: "shield"
                                onClicked: root.navigateRequested(2)
                            }
                            Item { Layout.fillWidth: true }
                            AppButton {
                                text: "Open the output folder"
                                small: true
                                variant: "ghost"
                                iconName: "folder"
                                onClicked: appBridge.openOutputFolder()
                            }
                        }
                    }
                }

                AppCard {
                    Layout.fillWidth: true
                    visible: appBridge.isRunning || appBridge.logText !== ""
                    title: "Live log"
                    headerExtra: [
                        AppSwitch {
                            text: "Follow"
                            checked: appBridge.logVisible
                            onToggled: appBridge.logVisible = checked
                            accessibleName: "Follow the log tail"
                        }
                    ]

                    ConsoleView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 190
                        query: ""
                        follow: appBridge.logVisible
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }

    // The pipeline column needs to know its own width for the card width.
    onWidthChanged: pipelineCardWidth = width

    property real pipelineCardWidth: 0

    // --- File dialogs -----------------------------------------------------
    FileDialog {
        id: inputFileMenu
        nameFilters: ["Media files (*.mp4 *.mkv *.webm *.mov *.avi *.mp3 *.m4a *.wav *.flac *.ogg)", "All files (*)"]
        onAccepted: appBridge.filePath = appBridge.localPath(selectedFile)
    }

    FileDialog {
        id: outputFileMenu
        fileMode: FileDialog.SaveFile
        nameFilters: ["Subtitles (*.srt *.ass)"]
        onAccepted: {
            const p = appBridge.localPath(selectedFile)
            outPathField.text = p
            appBridge.outPath = p
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
}
