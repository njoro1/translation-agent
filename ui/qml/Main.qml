import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "."
import "components"

ApplicationWindow {
    id: window

    readonly property bool isYouTubeMode: appBridge.pipelineMode === "youtube_cloud"
    readonly property bool isLocalMode: appBridge.pipelineMode !== "youtube_cloud"
    readonly property bool isOfflineMode: appBridge.pipelineMode === "offline"

    x: appBridge.windowX
    y: appBridge.windowY
    width: appBridge.windowWidth
    height: appBridge.windowHeight
    minimumWidth: 1024
    minimumHeight: 680
    visible: true
    title: "Translation Agent"
    color: Theme.background

    function switchToTab(index) {
        tabBar.currentIndex = index
    }

    onClosing: {
        appBridge.saveWindowState(
            Math.round(x) + "," + Math.round(y) + ","
            + Math.round(width) + "," + Math.round(height)
        )
    }

    // --- Header ---------------------------------------------------------------
    header: AppHeader {}

    // --- Workspace ------------------------------------------------------------
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        TabBar {
            id: tabBar
            objectName: "mainTabs"
            Layout.fillWidth: true

            background: Rectangle {
                color: Theme.background
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Theme.border
                }
            }

            TabButton {
                text: "Run"
                width: implicitWidth
                onClicked: window.switchToTab(0)

                background: Rectangle {
                    color: "transparent"
                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 2
                        color: tabBar.currentIndex === 0 ? Theme.accent : "transparent"
                    }
                }

                contentItem: Label {
                    text: parent.text
                    color: tabBar.currentIndex === 0 ? Theme.text : Theme.textMuted
                    font.pixelSize: Theme.fontLabel
                    font.bold: tabBar.currentIndex === 0
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            TabButton {
                text: "Review"
                width: implicitWidth
                onClicked: window.switchToTab(1)

                background: Rectangle {
                    color: "transparent"
                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 2
                        color: tabBar.currentIndex === 1 ? Theme.accent : "transparent"
                    }
                }

                contentItem: Label {
                    text: parent.text
                    color: tabBar.currentIndex === 1 ? Theme.text : Theme.textMuted
                    font.pixelSize: Theme.fontLabel
                    font.bold: tabBar.currentIndex === 1
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            TabButton {
                text: "Quality"
                width: implicitWidth
                onClicked: window.switchToTab(2)

                background: Rectangle {
                    color: "transparent"
                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: 2
                        color: tabBar.currentIndex === 2 ? Theme.accent : "transparent"
                    }
                }

                contentItem: Label {
                    text: parent.text
                    color: tabBar.currentIndex === 2 ? Theme.text : Theme.textMuted
                    font.pixelSize: Theme.fontLabel
                    font.bold: tabBar.currentIndex === 2
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabBar.currentIndex

            // ================= RUN TAB =================
            Item {
                id: runTab

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.lg
                    spacing: Theme.lg

                    // --- Left column: configuration ---
                    ScrollView {
                        Layout.preferredWidth: 400
                        Layout.fillHeight: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        ScrollBar.vertical.policy: ScrollBar.AlwaysOn

                        ColumnLayout {
                            width: 400 - Theme.md
                            spacing: Theme.md

                            SectionPanel {
                                title: "Source"
                                Layout.fillWidth: true

                                ColumnLayout {
                                    width: parent.width
                                    spacing: Theme.sm

                                    RowLayout {
                                        visible: window.isYouTubeMode
                                        Layout.fillWidth: true
                                        spacing: Theme.sm

                                        FieldLabel { text: "URL"; Layout.preferredWidth: 60 }
                                        CompactTextField {
                                            id: urlField
                                            Layout.fillWidth: true
                                            text: appBridge.url
                                            placeholderText: "https://www.youtube.com/watch?v=…"
                                            onEditingFinished: appBridge.url = text
                                            // Auto-parse: once the URL stops
                                            // changing (covers paste + typing),
                                            // inspect formats automatically.
                                            onTextEdited: {
                                                appBridge.url = text
                                                urlAutoParseTimer.restart()
                                            }

                                            Timer {
                                                id: urlAutoParseTimer
                                                interval: 800
                                                repeat: false
                                                onTriggered: {
                                                    if (window.isYouTubeMode
                                                            && urlField.text.trim() !== ""
                                                            && !appBridge.youtubeInfoLoading
                                                            && !appBridge.youtubeDownloading) {
                                                        appBridge.fetchYouTubeInfo()
                                                    }
                                                }
                                            }
                                        }
                                    }

                                    RowLayout {
                                        visible: !window.isYouTubeMode
                                        Layout.fillWidth: true
                                        spacing: Theme.sm

                                        FieldLabel { text: "File"; Layout.preferredWidth: 60 }
                                        CompactTextField {
                                            id: filePathField
                                            Layout.fillWidth: true
                                            readOnly: true
                                            text: appBridge.filePath
                                            placeholderText: "Drop a media file here or Browse"
                                        }
                                        Button {
                                            text: "Browse"
                                            onClicked: inputFileMenu.open()

                                            background: Rectangle {
                                                radius: Theme.radiusSm
                                                color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                                                border.color: Theme.border
                                            }
                                            contentItem: Label {
                                                text: parent.text
                                                color: Theme.text
                                                font.pixelSize: Theme.fontSmall
                                                horizontalAlignment: Text.AlignHCenter
                                                verticalAlignment: Text.AlignVCenter
                                            }

                                            FileDialog {
                                                id: inputFileMenu
                                                nameFilters: ["Media files (*.mp4 *.mkv *.webm *.mov *.avi *.mp3 *.m4a *.wav *.flac *.ogg)", "All files (*)"]
                                                onAccepted: appBridge.filePath = appBridge.localPath(selectedFile)
                                            }
                                        }
                                    }

                                    RowLayout {
                                        visible: window.isLocalMode
                                        Layout.fillWidth: true
                                        spacing: Theme.sm

                                        FieldLabel { text: "ASR lang"; Layout.preferredWidth: 60 }
                                        CompactComboBox {
                                            Layout.fillWidth: true
                                            editable: true
                                            editText: appBridge.asrLanguage
                                            model: ["auto", "zh", "en", "ja", "ko", "yue"]
                                            onAccepted: appBridge.asrLanguage = editText.trim() || "auto"
                                            onActivated: appBridge.asrLanguage = editText.trim() || "auto"
                                        }
                                    }
                                }
                            }

                            SectionPanel {
                                title: "Output"
                                Layout.fillWidth: true

                                ColumnLayout {
                                    width: parent.width
                                    spacing: Theme.sm

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.sm

                                        FieldLabel { text: "Path"; Layout.preferredWidth: 60 }
                                        CompactTextField {
                                            id: outPathField
                                            Layout.fillWidth: true
                                            text: appBridge.outPath
                                            placeholderText: "Auto-named from the title"
                                            onEditingFinished: appBridge.outPath = appBridge.localPath(text)
                                        }
                                        Button {
                                            text: "…"
                                            implicitWidth: 30
                                            onClicked: outputFileMenu.open()

                                            background: Rectangle {
                                                color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                                                radius: Theme.radiusSm
                                                border.color: Theme.border
                                            }
                                            contentItem: Label { text: "…"; color: Theme.text; horizontalAlignment: Text.AlignHCenter }
                                        }
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

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: Theme.sm

                                        FieldLabel { text: "Format"; Layout.preferredWidth: 60 }
                                        CompactComboBox {
                                            Layout.preferredWidth: 100
                                            model: ["srt", "ass"]
                                            currentIndex: appBridge.outputFormat === "ass" ? 1 : 0
                                            onActivated: appBridge.outputFormat = currentText
                                        }

                                        Item { Layout.fillWidth: true }

                                        Button {
                                            visible: appBridge.canOpenOutputFolder
                                            text: "Open folder"
                                            onClicked: appBridge.openOutputFolder()

                                            background: Rectangle {
                                                radius: Theme.radiusSm
                                                color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                                                border.color: Theme.border
                                            }
                                            contentItem: Label {
                                                text: parent.text
                                                color: Theme.text
                                                font.pixelSize: Theme.fontSmall
                                                horizontalAlignment: Text.AlignHCenter
                                                verticalAlignment: Text.AlignVCenter
                                            }
                                        }
                                    }
                                }
                            }

                            YouTubeVideoPanel {}

                            SectionPanel {
                                title: "Translation"
                                Layout.fillWidth: true

                                ColumnLayout {
                                    width: parent.width
                                    spacing: Theme.sm

                                    Label {
                                        Layout.fillWidth: true
                                        wrapMode: Text.WordWrap
                                        font.pixelSize: Theme.fontSmall
                                        color: Theme.textMuted
                                        text: {
                                            if (window.isOfflineMode)
                                                return "Local llama.cpp translation (Hy-MT2). No cloud calls."
                                            if (appBridge.model !== "")
                                                return "Cloud LLM: " + appBridge.model
                                            return "Cloud LLM (model from .env or Advanced settings)."
                                        }
                                    }

                                    RowLayout {
                                        visible: window.isOfflineMode
                                        Layout.fillWidth: true
                                        spacing: Theme.sm

                                        Label {
                                            text: appBridge.localModelReady
                                                  ? "\u2713 Local model ready"
                                                  : "! No local translation model"
                                            color: appBridge.localModelReady ? Theme.success : Theme.warning
                                            font.pixelSize: Theme.fontSmall
                                        }

                                        Item { Layout.fillWidth: true }

                                        Button {
                                            visible: !appBridge.localModelReady
                                            enabled: !appBridge.localModelDownloading
                                            text: appBridge.localModelDownloading ? "Downloading…" : "Download"
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
                                        visible: window.isLocalMode && !appBridge.asrModelReady
                                        Layout.fillWidth: true
                                        spacing: Theme.sm

                                        Label {
                                            text: "! ASR model missing"
                                            color: Theme.warning
                                            font.pixelSize: Theme.fontSmall
                                        }

                                        Item { Layout.fillWidth: true }

                                        Button {
                                            enabled: !appBridge.modelDownloading
                                            text: appBridge.modelDownloading ? "Downloading…" : "Download ASR models"
                                            onClicked: appBridge.downloadAsrModels()

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
                                }
                            }

                            AdvancedDrawer {
                                objectName: "advancedDrawer"
                                Layout.fillWidth: true
                            }

                            Item { Layout.preferredHeight: 1 }
                        }
                    }

                    // --- Right column: state / progress / result ---
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        DropArea {
                            id: dropArea
                            width: parent.width
                            height: runRightColumn.implicitHeight + Theme.xl
                            enabled: !window.isYouTubeMode
                            onDropped: (drop) => {
                                if (drop.hasUrls && drop.urls.length > 0) {
                                    appBridge.filePath = appBridge.localPath(drop.urls[0])
                                }
                            }

                            ColumnLayout {
                                id: runRightColumn
                                x: Theme.md
                                y: Theme.md
                                width: dropArea.width - Theme.xl
                                spacing: Theme.lg

                                // Readiness (before/during any run)
                                SectionPanel {
                                    title: "Readiness"
                                    Layout.fillWidth: true

                                    ReadinessChecklist {}
                                }

                                // Progress (during run)
                                SectionPanel {
                                    title: "Progress"
                                    Layout.fillWidth: true
                                    visible: appBridge.isRunning || appBridge.statusState === "done" || appBridge.statusState === "failed"

                                    ProgressPanel {}
                                }

                                // Result summary card
                                SectionPanel {
                                    title: "Result"
                                    Layout.fillWidth: true
                                    visible: appBridge.resultReady

                                    ColumnLayout {
                                        width: parent.width
                                        spacing: Theme.sm

                                        Label {
                                            Layout.fillWidth: true
                                            elide: Text.ElideMiddle
                                            text: appBridge.outputPathResolved
                                            color: Theme.text
                                            font.pixelSize: Theme.fontBody
                                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 4
                            columnSpacing: Theme.md
                            rowSpacing: Theme.xs

                            ColumnLayout {
                                spacing: 0
                                Label { text: String(appBridge.qualityTotalCues); color: Theme.text; font.pixelSize: Theme.fontTitle; font.bold: true }
                                Label { text: "cues"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            }
                            ColumnLayout {
                                spacing: 0
                                Label { text: String(appBridge.qualityUntranslated); color: appBridge.qualityUntranslated > 0 ? Theme.error : Theme.success; font.pixelSize: Theme.fontTitle; font.bold: true }
                                Label { text: "untranslated"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            }
                            ColumnLayout {
                                spacing: 0
                                Label { text: String(appBridge.qualityWarnings); color: appBridge.qualityWarnings > 0 ? Theme.warning : Theme.success; font.pixelSize: Theme.fontTitle; font.bold: true }
                                Label { text: "warnings"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            }
                            ColumnLayout {
                                spacing: 0
                                Label {
                                    text: appBridge.resultStrictState === "pass" ? "PASS"
                                        : appBridge.resultStrictState === "fail" ? "FAIL" : "OFF"
                                    color: appBridge.resultStrictState === "fail" ? Theme.error
                                        : appBridge.resultStrictState === "pass" ? Theme.success : Theme.textMuted
                                    font.pixelSize: Theme.fontTitle; font.bold: true
                                }
                                Label { text: "strict"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            }
                        }

                                        RowLayout {
                                            spacing: Theme.sm

                                            Button {
                                                text: "Open Output Folder"
                                                onClicked: appBridge.openOutputFolder()

                                                background: Rectangle {
                                                    radius: Theme.radiusSm
                                                    color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                                                    border.color: Theme.border
                                                }
                                                contentItem: Label {
                                                    text: parent.text
                                                    color: Theme.text
                                                    font.pixelSize: Theme.fontSmall
                                                    horizontalAlignment: Text.AlignHCenter
                                                    verticalAlignment: Text.AlignVCenter
                                                }
                                            }

                                            Button {
                                                text: "View Review"
                                                onClicked: window.switchToTab(1)

                                                background: Rectangle {
                                                    radius: Theme.radiusSm
                                                    color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                                                    border.color: Theme.border
                                                }
                                                contentItem: Label {
                                                    text: parent.text
                                                    color: Theme.text
                                                    font.pixelSize: Theme.fontSmall
                                                    horizontalAlignment: Text.AlignHCenter
                                                    verticalAlignment: Text.AlignVCenter
                                                }
                                            }

                                            Button {
                                                text: "View Quality"
                                                onClicked: window.switchToTab(2)

                                                background: Rectangle {
                                                    radius: Theme.radiusSm
                                                    color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                                                    border.color: Theme.border
                                                }
                                                contentItem: Label {
                                                    text: parent.text
                                                    color: Theme.text
                                                    font.pixelSize: Theme.fontSmall
                                                    horizontalAlignment: Text.AlignHCenter
                                                    verticalAlignment: Text.AlignVCenter
                                                }
                                            }
                                        }
                                    }
                                }

                                Item { Layout.fillHeight: true }
                            }
                        }
                    }
                }
            }

            // ================= REVIEW TAB =================
            Item {
                CuePreviewTable {
                    anchors.fill: parent
                    anchors.margins: Theme.lg
                }
            }

            // ================= QUALITY TAB =================
            Item {
                QualityPanel {
                    anchors.fill: parent
                    anchors.margins: Theme.lg
                }
            }
        }

        // Bottom log drawer (collapsed by default)
        LogDrawer {
            Layout.fillWidth: true
        }
    }
}
