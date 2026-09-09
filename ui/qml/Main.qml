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

    // Theme is a QML singleton and must not depend on the `appBridge` context
    // property, so the persisted appearance is pushed into it from here.
    Binding { target: Theme; property: "themeName"; value: appBridge.themeName }
    Binding { target: Theme; property: "comfortable"; value: appBridge.comfortable }
    Binding { target: Theme; property: "reducedMotion"; value: appBridge.reducedMotion }

    // Bridge-initiated navigation (error card -> Run tab, reveal Advanced).
    Connections {
        target: appBridge
        function onRequestTab(index) { window.switchToTab(index) }
        function onRequestAdvanced() {
            advancedDrawer.expanded = true
            window.switchToTab(0)
        }
    }

    // Global keyboard shortcuts (U-18).
    Shortcut { sequence: "Ctrl+1"; context: Qt.ApplicationShortcut; onActivated: window.switchToTab(0) }
    Shortcut { sequence: "Ctrl+2"; context: Qt.ApplicationShortcut; onActivated: window.switchToTab(1) }
    Shortcut { sequence: "Ctrl+3"; context: Qt.ApplicationShortcut; onActivated: window.switchToTab(2) }
    Shortcut {
        sequence: "Ctrl+R"
        context: Qt.ApplicationShortcut
        onActivated: if (!appBridge.isRunning) appBridge.runTranslation()
    }
    Shortcut {
        sequence: "Ctrl+."
        context: Qt.ApplicationShortcut
        onActivated: if (appBridge.isRunning) appBridge.cancelRun()
    }
    Shortcut {
        sequence: "Ctrl+F"
        context: Qt.ApplicationShortcut
        onActivated: window.switchToTab(1)
    }
    Shortcut {
        sequence: "Ctrl+L"
        context: Qt.ApplicationShortcut
        onActivated: appBridge.logVisible = true
    }

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
                    // Split view: config column + flexible result column.
                    // The config column grows on wide windows (up to 480px)
                    // instead of pinning dead space beside a fixed 400px.
                    ScrollView {
                        Layout.fillHeight: true
                        Layout.preferredWidth: 440
                        Layout.maximumWidth: 480
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        ScrollBar.vertical.policy: ScrollBar.AlwaysOn

                        ColumnLayout {
                            width: 440 - Theme.md
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
                                            label: "YouTube URL"
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
                                            label: "Input file path"
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

                            // 3-step flow strip (U-12): orients first-time YouTube users.
                            Label {
                                visible: window.isYouTubeMode
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                                font.pixelSize: Theme.fontSmall
                                color: Theme.textMuted
                                text: "1 · Paste a YouTube URL above and Inspect formats   →   " +
                                      "2 · (Optional) pick a video format   →   " +
                                      "3 · Download the English subtitle, then translate it"
                            }

                            YouTubeVideoPanel {}

                            YouTubeSubtitlePanel {}

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
                                        visible: window.isLocalMode
                                        Layout.fillWidth: true
                                        spacing: Theme.sm

                                        FieldLabel { text: "Source override"; Layout.preferredWidth: 120 }
                                        CompactComboBox {
                                            Layout.fillWidth: true
                                            editable: true
                                            editText: appBridge.sourceLang
                                            model: ["", "ja", "zh", "zh-TW", "ko", "yue", "en"]
                                            onAccepted: appBridge.sourceLang = editText.trim()
                                            onActivated: appBridge.sourceLang = editText.trim()
                                            ToolTip.visible: hovered
                                            ToolTip.delay: 500
                                            ToolTip.text: "Override the translation source language. Blank = use the spoken (ASR) language set above."
                                            Accessible.name: "Translation source language override"
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
                    // DropArea covers the whole pane (it used to hug the
                    // content column, so drops landing in empty space were
                    // ignored and the pane was dead white space until a run
                    // finished — now there is first-run guidance too).
                    Item {
                        id: rightPane
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        DropArea {
                            id: dropArea
                            anchors.fill: parent
                            enabled: !window.isYouTubeMode
                            onDropped: (drop) => {
                                if (drop.hasUrls && drop.urls.length > 0) {
                                    appBridge.filePath = appBridge.localPath(drop.urls[0])
                                }
                            }
                        }

                        ScrollView {
                            anchors.fill: parent
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                            ColumnLayout {
                                id: runRightColumn
                                x: Theme.md
                                y: Theme.md
                                width: rightPane.width - Theme.xl
                                spacing: Theme.lg

                                // Readiness (before/during any run)
                                SectionPanel {
                                    title: "Readiness"
                                    Layout.fillWidth: true

                                    ReadinessChecklist {}
                                }

                                // First-run guidance for the previously empty
                                // right column.
                                Label {
                                    Layout.fillWidth: true
                                    visible: !appBridge.isRunning && !appBridge.resultReady
                                    horizontalAlignment: Text.AlignHCenter
                                    wrapMode: Text.WordWrap
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.fontBody
                                    text: window.isYouTubeMode
                                          ? "Paste a YouTube URL on the left, download its subtitles, then press Run."
                                          : "Drop a video/audio file anywhere here, or pick one on the left, then press Run."
                                }

                                // Structured failure (replaces "see the log")
                                ErrorCard {}

                                // Progress (during run)
                                SectionPanel {
                                    title: "Progress"
                                    Layout.fillWidth: true
                                    visible: appBridge.isRunning || appBridge.statusState === "done" || appBridge.statusState === "failed" || appBridge.statusState === "cancelled"

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
