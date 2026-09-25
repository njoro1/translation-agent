import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."
import "../components"

// Run screen: Source -> Processing -> Inspector.
//
// Three structural fixes from the UI review live here:
//
//  * 6.1 — Source and Engine are two independent selectors. The old flattened
//    3-cell control (`YouTube Cloud` / `Local Cloud` / `Offline`) conflated two
//    orthogonal axes, which produced the "Local Cloud" oxymoron and hid the
//    fourth combination entirely.
//  * 2.4 — ONE whole-screen scroll, not three independent column scrolls. With
//    independent scrolls, scrolling a column scrolled its header away, which is
//    why the `2` header appeared to clip off the top in some modes while `1`
//    and `3` stayed. All columns now share one grid and one scroll.
//  * 6.2 — The SOURCE panel uses a StackLayout, whose implicit height is the
//    maximum of its children, so toggling YouTube <-> local swaps CONTENT, not
//    LAYOUT. The old panel changed shape drastically between modes, which made
//    the left third jump and destroyed muscle memory.
Item {
    id: root

    readonly property bool isYouTubeMode: appBridge.runSource === "youtube"
    readonly property bool isLocalEngine: appBridge.runEngine === "local"
    readonly property bool isOfflineMode: appBridge.pipelineMode === "offline"
    readonly property bool hasResult: appBridge.resultReady

    // Readiness is a passive validator, not step 3 of a sequence (6.4). The
    // denominator counts real checks only, so it always matches the rows shown.
    readonly property int readyOk: appBridge.readinessReadyCount
    readonly property int readyRequired: appBridge.readinessActionableCount
    readonly property int readyNa: appBridge.readinessNotApplicableCount

    signal navigateRequested(int page)
    signal openSettingsRequested(string section)

    // =====================================================================
    // One scroll for the whole screen (2.4).
    Flickable {
        id: runFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: columns.implicitHeight + 36
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        RowLayout {
            id: columns
            x: 18
            y: 18
            width: runFlick.width - 36
            spacing: 16

            // ------------------------------------------------------ SOURCE --
            ColumnLayout {
                Layout.preferredWidth: 364
                Layout.minimumWidth: 300
                spacing: 16

                AppCard {
                    id: sourceCard
                    objectName: "run.sourceCard"
                    Layout.fillWidth: true
                    title: "Source"
                    stepNumber: 1
                    active: !root.isYouTubeMode || appBridge.url !== ""
                    headerExtra: [
                        Chip {
                            text: appBridge.sourceEngineSummary
                            tone: "acc"
                        }
                    ]

                    ColumnLayout {
                        objectName: "run.sourceContent"
                        width: parent.width
                        spacing: 12

                        // --- Axis 1: where the subtitles come from ----------
                        RowLayout {
                            objectName: "run.sourceAxis1"
                            Layout.fillWidth: true
                            spacing: 8

                            Label {
                                text: "Source"
                                Layout.preferredWidth: 56
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSmall
                            }

                            SegmentedControl {
                                objectName: "bound.run.source"
                                options: [
                                    { id: "youtube", label: "YouTube URL" },
                                    { id: "localfile", label: "Local file" }
                                ]
                                current: appBridge.runSource
                                onActivated: (id) => {
                                    const problem = appBridge.setRunSource(id)
                                    if (problem !== "")
                                        appBridge.setStatusMessage(problem)
                                }
                                Accessible.name: "Where the subtitles come from"
                            }
                            Item { Layout.fillWidth: true }
                        }

                        // --- Axis 2: which engine translates them -----------
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Label {
                                text: "Engine"
                                Layout.preferredWidth: 56
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSmall
                            }

                            SegmentedControl {
                                objectName: "bound.run.engine"
                                options: [
                                    { id: "cloud", label: "Cloud LLM" },
                                    { id: "local", label: "Local model" }
                                ]
                                // The 4th matrix cell is disabled-with-reason,
                                // not silently impossible (6.1). The reason is
                                // rendered just below.
                                disabledIds: appBridge.engineLocalDisabledReason !== ""
                                             ? ["local"] : []
                                current: appBridge.runEngine
                                onActivated: (id) => {
                                    const problem = appBridge.setRunEngine(id)
                                    if (problem !== "")
                                        appBridge.setStatusMessage(problem)
                                }
                                Accessible.name: "Which engine translates the subtitles"
                            }
                            Item { Layout.fillWidth: true }
                        }

                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

                        // --- Language pair: present in EVERY mode -----------
                        // It used to live only inside the local-file block, which
                        // left the top-bar dropdowns as orphaned authority (6.3).
                        RowLayout {
                            objectName: "run.languageRow"
                            Layout.fillWidth: true
                            spacing: 8

                            Label {
                                text: root.isYouTubeMode ? "Subtitles" : "Spoken"
                                Layout.preferredWidth: 56
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSmall
                            }
                            BoundField {
                                objectName: "bound.run.language"
                                Layout.fillWidth: true
                                label: root.isYouTubeMode
                                       ? "Language of the source subtitles"
                                       : "Spoken language the ASR transcribes"
                                model: ["auto", "ja", "zh", "zh-TW", "ko", "yue", "en"]
                                readValue: function() {
                                    return root.isYouTubeMode
                                           ? appBridge.sourceLang
                                           : appBridge.asrLanguage
                                }
                                writeValue: function(v) {
                                    if (root.isYouTubeMode) appBridge.sourceLang = v
                                    else appBridge.asrLanguage = v
                                }
                                ToolTip.visible: hovered
                                ToolTip.delay: 500
                                ToolTip.text: root.isYouTubeMode
                                    ? "Language of the subtitles to translate (auto = detect)."
                                    : "Spoken language the ASR transcribes (auto = detect)."
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Label {
                                text: "Output"
                                Layout.preferredWidth: 56
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSmall
                            }
                            // An invariant, not a control (1.3).
                            Label {
                                Layout.fillWidth: true
                                text: "Always English."
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSmall
                                wrapMode: Text.WordWrap
                            }
                        }

                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

                        // --- Mode-specific body, constant height ------------
                        // A StackLayout sizes itself to the CURRENT child, not to
                        // the tallest one (measured: 387 px in YouTube mode,
                        // 343 px for a local file), so on its own it still lets
                        // the panel jump when the mode flips. `reservedHeight` is
                        // a high-water mark: it grows to the tallest branch ever
                        // seen and never shrinks, which is the "fixed skeleton"
                        // the review asked for (2.4). YouTube is the default
                        // source, so the taller branch is measured first.
                        StackLayout {
                            objectName: "run.sourceBody"
                            Layout.fillWidth: true
                            currentIndex: root.isYouTubeMode ? 0 : 1

                            property real reservedHeight: 0
                            readonly property real tallest: Math.max(
                                youtubeBody.implicitHeight,
                                localBody.implicitHeight)
                            onTallestChanged: reservedHeight = Math.max(reservedHeight, tallest)
                            Layout.preferredHeight: reservedHeight

                            // ==== YouTube ==================================
                            ColumnLayout {
                                id: youtubeBody
                                spacing: 8

                                // Why the local engine cannot be picked in this
                                // mode (6.1). It lives INSIDE the constant-height
                                // body, and carries no `visible` guard, for the
                                // same reason the download header does: a
                                // conditional height here changes the StackLayout
                                // maximum and the SOURCE card jumps.
                                Label {
                                    Layout.fillWidth: true
                                    text: appBridge.engineLocalDisabledReason
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.fontTiny
                                    wrapMode: Text.WordWrap
                                }

                                CompactTextField {
                                    id: urlField
                                    Layout.fillWidth: true
                                    label: "YouTube URL"
                                    text: appBridge.url
                                    placeholderText: "https://www.youtube.com/watch?v=\u2026"
                                    onEditingFinished: appBridge.url = text
                                    onTextEdited: {
                                        appBridge.url = text
                                        urlAutoParseTimer.restart()
                                    }

                                    // Auto-parse: once the URL stops changing
                                    // (covers paste + typing), inspect the formats.
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
                                        text: appBridge.youtubeInfoLoading ? "Inspecting\u2026" : "Inspect"
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
                                                ToolTip.visible: titleHover.hovered && appBridge.youtubeTitle !== ""
                                                ToolTip.delay: 500
                                                ToolTip.text: appBridge.youtubeTitle
                                                HoverHandler { id: titleHover }
                                            }

                                            RowLayout {
                                                spacing: 6

                                                StatusMark {
                                                    visible: appBridge.youtubeHasInfo
                                                    small: true
                                                    status: appBridge.youtubeHasEnglishSubtitle ? "ok" : "todo"
                                                    text: appBridge.youtubeHasEnglishSubtitle
                                                          ? "English track found" : "No English track"
                                                }
                                            }
                                        }
                                    }
                                }

                                // ==== Inspect result (6.3) =================
                                // After inspect, show what was actually found
                                // inline, so `Download English subtitle` has a
                                // visible reason to be enabled or disabled.
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    visible: appBridge.youtubeHasInfo
                                    spacing: 6

                                    Label {
                                        text: "SUBTITLE SOURCE"
                                        color: Theme.textMuted
                                        font.pixelSize: 10
                                        font.bold: true
                                        font.letterSpacing: 0.8
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        StatusMark {
                                            status: appBridge.youtubeHasEnglishSubtitle ? "ok" : "todo"
                                            text: appBridge.youtubeHasEnglishSubtitle
                                                  ? "English subtitle track"
                                                  : "No English subtitle track"
                                            small: true
                                        }
                                        Item { Layout.fillWidth: true }
                                        Chip {
                                            visible: appBridge.youtubeHasEnglishSubtitle
                                            text: appBridge.youtubeSelectedFormatLabel !== ""
                                                  ? appBridge.youtubeSelectedFormatLabel
                                                  : "best available"
                                            mono: true
                                        }
                                    }

                                    Label {
                                        Layout.fillWidth: true
                                        visible: !appBridge.youtubeHasEnglishSubtitle
                                        text: "This video has no English subtitle track. Download the "
                                              + "video below and switch the source to a local file to "
                                              + "transcribe it instead."
                                        color: Theme.warning
                                        font.pixelSize: Theme.fontTiny
                                        wrapMode: Text.WordWrap
                                    }
                                }

                                YouTubeSubtitlePanel {
                                    Layout.fillWidth: true
                                }

                                // --- Optional video download (6.3) ----------
                                // Inside the constant-height body on purpose: as
                                // a sibling of the StackLayout this header added
                                // 28px + 12px of spacing in YouTube mode only,
                                // so the whole SOURCE card jumped 40px when the
                                // source axis flipped (2.4). The `visible` guard
                                // is gone for the same reason — the branch is
                                // only rendered in YouTube mode anyway, and the
                                // StackLayout must count this height in *both*
                                // modes for the max to be stable.
                                Item {
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
                                    visible: expanded
                                    Layout.fillWidth: true
                                    spacing: 8

                                    YouTubeVideoPanel {
                                        Layout.fillWidth: true
                                    }
                                }
                            }

                            // ==== Local file ===============================
                            ColumnLayout {
                                id: localBody
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
                                        ToolTip.visible: fileHover.hovered && appBridge.filePath !== ""
                                        ToolTip.delay: 500
                                        ToolTip.text: appBridge.filePath
                                        HoverHandler { id: fileHover }
                                    }

                                    Chip {
                                        visible: appBridge.filePath !== ""
                                        text: appBridge.fileSizeText
                                        mono: true
                                    }
                                }
                            }
                        }

                    }
                }

                Item { Layout.fillHeight: true }
            }

            // -------------------------------------------------- PROCESSING --
            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 340
                spacing: 16

                AppCard {
                    id: processingCard
                    objectName: "run.processingCard"
                    Layout.fillWidth: true
                    // `PIPELINE` was a form, not a flow (6.2). The strip below is
                    // the part that actually honours the name.
                    title: "Processing"
                    stepNumber: 2
                    active: root.readyOk === root.readyRequired && root.readyRequired > 0

                    ColumnLayout {
                        width: parent.width
                        spacing: 14

                        StageStrip {
                            Layout.fillWidth: true
                        }

                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

                        // --- Output ----------------------------------------
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
                                    placeholderText: "Saved next to the video"
                                    label: "Output file path"
                                    onEditingFinished: appBridge.outPath = appBridge.localPath(text)
                                }
                                AppButton {
                                    visible: !appBridge.outPathAuto
                                    text: "Auto"
                                    small: true
                                    variant: "ghost"
                                    iconName: "refresh"
                                    onClicked: appBridge.useAutoOutPath()
                                    Accessible.name: "Save next to the video again"
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

                            Label {
                                Layout.fillWidth: true
                                Layout.leftMargin: 74
                                visible: appBridge.outPathHint !== ""
                                text: appBridge.outPathHint
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontTiny
                                wrapMode: Text.WordWrap
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Label { text: "Format"; Layout.preferredWidth: 66; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                                BoundComboBox {
                                    objectName: "bound.run.outputFormat"
                                    Layout.preferredWidth: 110
                                    label: "Output format"
                                    model: ["srt", "ass"]
                                    readValue: function() { return appBridge.outputFormat }
                                    writeValue: function(v) { appBridge.outputFormat = v }
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

                        // --- Translation ------------------------------------
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
                                        tone: root.isLocalEngine ? "acc" : "info"
                                        text: root.isLocalEngine ? "Local llama.cpp" : "Cloud LLM"
                                    }

                                    Label {
                                        Layout.fillWidth: true
                                        // Provenance lives in Settings now; the Run
                                        // screen shows the model in effect without
                                        // leaking `.env` file mechanics (1.4, 5.7).
                                        text: root.isLocalEngine
                                              ? appBridge.modelName
                                              : appBridge.effectiveModelText
                                        color: Theme.textDim
                                        font.pixelSize: Theme.fontSmall
                                        font.family: Theme.monoFont
                                        elide: Text.ElideRight
                                        ToolTip.visible: modelHover.hovered
                                        ToolTip.delay: 500
                                        ToolTip.text: root.isLocalEngine
                                            ? appBridge.modelName
                                            : appBridge.effectiveModelText
                                        HoverHandler { id: modelHover }
                                    }
                                }
                            }

                            // Local translation model state + download. This is a
                            // SECONDARY action: it no longer hijacks the global
                            // primary button (3.3).
                            RowLayout {
                                visible: root.isLocalEngine
                                Layout.fillWidth: true
                                spacing: 8

                                StatusMark {
                                    status: appBridge.localModelReady ? "ok" : "todo"
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: appBridge.localModelReady
                                          ? "Hy-MT2 translation model ready"
                                          : appBridge.localModelCorrupt
                                            ? "Translation model file is incomplete \u2014 re-download it"
                                            : "No local translation model"
                                    color: appBridge.localModelReady ? Theme.textDim : Theme.warning
                                    font.pixelSize: Theme.fontSmall
                                    wrapMode: Text.WordWrap
                                }
                                AppButton {
                                    visible: !appBridge.localModelReady
                                    text: appBridge.localModelDownloading
                                          ? "Downloading\u2026"
                                          : (appBridge.localModelCorrupt ? "Re-download" : "Download")
                                    small: true
                                    variant: "primary"
                                    iconName: "download"
                                    enabled: !appBridge.localModelDownloading
                                    onClicked: appBridge.downloadLocalModel()
                                }
                            }

                            Label {
                                visible: root.isLocalEngine && appBridge.localModelCorrupt
                                         && appBridge.localModelProblem !== ""
                                Layout.fillWidth: true
                                text: appBridge.localModelProblem
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontTiny
                                wrapMode: Text.WordWrap
                            }

                            // ASR model state + download (local source only).
                            RowLayout {
                                visible: !root.isYouTubeMode && !appBridge.asrModelReady
                                Layout.fillWidth: true
                                spacing: 8

                                StatusMark { status: "todo" }
                                Label {
                                    Layout.fillWidth: true
                                    text: appBridge.asrModelCorrupt
                                          ? "ASR model file is incomplete \u2014 re-download it"
                                          : "ASR model missing"
                                    color: Theme.warning
                                    font.pixelSize: Theme.fontSmall
                                    wrapMode: Text.WordWrap
                                }
                                AppButton {
                                    text: appBridge.modelDownloading
                                          ? "Downloading\u2026"
                                          : (appBridge.asrModelCorrupt
                                             ? "Re-download ASR models"
                                             : "Download ASR models")
                                    small: true
                                    variant: "primary"
                                    iconName: "download"
                                    enabled: !appBridge.modelDownloading
                                    onClicked: appBridge.downloadAsrModels()
                                }
                            }

                            Label {
                                visible: !root.isYouTubeMode && appBridge.asrModelCorrupt
                                         && appBridge.asrModelProblem !== ""
                                Layout.fillWidth: true
                                text: appBridge.asrModelProblem
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontTiny
                                wrapMode: Text.WordWrap
                            }

                            RowLayout {
                                visible: !root.isYouTubeMode && appBridge.asrModelReady
                                Layout.fillWidth: true
                                spacing: 8

                                StatusMark { status: "ok" }
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
                                BoundComboBox {
                                    objectName: "bound.run.contextMode"
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
                                    readValue: function() { return appBridge.contextMode }
                                    writeValue: function(v) { appBridge.contextMode = v }
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
                                BoundComboBox {
                                    objectName: "bound.run.translationMemory"
                                    Layout.preferredWidth: 130
                                    label: "Translation memory"
                                    textRole: "label"
                                    valueRole: "id"
                                    model: [
                                        { id: "auto", label: "Auto" },
                                        { id: "on", label: "On" },
                                        { id: "off", label: "Off" }
                                    ]
                                    readValue: function() { return appBridge.translationMemoryMode }
                                    writeValue: function(v) { appBridge.translationMemoryMode = v }
                                }

                                Label { text: "Glossary"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                                // One control, not a field + a "Choose" button (6.5).
                                AppButton {
                                    Layout.fillWidth: true
                                    text: appBridge.glossaryPath === ""
                                          ? "Choose glossary\u2026"
                                          : appBridge.glossaryPath.split(/[\\/]/).pop()
                                    small: true
                                    variant: "ghost"
                                    iconName: "folder"
                                    onClicked: glossaryDialog.open()
                                    Accessible.name: appBridge.glossaryPath === ""
                                        ? "Choose a glossary file"
                                        : "Change the glossary file (" + appBridge.glossaryPath + ")"
                                }
                            }

                            // Wraps instead of clipping: two long switch labels do not
                            // fit side by side in this column (2.2).
                            Flow {
                                Layout.fillWidth: true
                                spacing: 18

                                AppSwitch {
                                    text: "Strict quality gate (errors fail the run)"
                                    checked: appBridge.strictQuality
                                    onToggled: appBridge.strictQuality = checked
                                }

                                AppSwitch {
                                    text: "Rolling scene summary"
                                    checked: appBridge.contextSummary
                                    onToggled: appBridge.contextSummary = checked
                                    accessibleName: "Rolling scene summary (cloud, experimental)"
                                }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

                        // --- Content preset ---------------------------------
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

                            // Chips are the only editor: the parallel "Auto · detect"
                            // dropdown that mirrored them is gone (6.5).
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

                        // --- Advanced pointer ---------------------------------
                        // A link into the bound Settings category, not a floating
                        // button over the footer text (2.4, 6.5).
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
                                variant: "link"
                                iconName: "settings"
                                onClicked: root.openSettingsRequested("translation")
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }

            // --------------------------------------------------- INSPECTOR --
            ColumnLayout {
                Layout.preferredWidth: 332
                Layout.minimumWidth: 300
                spacing: 16

                // Readiness is a derived validator, so it is NOT numbered as a
                // step (6.4). `1 Source` and `2 Processing` are things the user
                // does; this is a passive check on whether they can.
                AppCard {
                    objectName: "run.readinessCard"
                    Layout.fillWidth: true
                    title: "Readiness"
                    active: root.readyOk === root.readyRequired && root.readyRequired > 0
                    headerExtra: [
                        Pill {
                            objectName: "run.readinessBadge"
                            tone: root.readyOk === root.readyRequired && root.readyRequired > 0
                                  ? "ok" : "warn"
                            text: root.readyOk + " of " + root.readyRequired + " actionable"
                                  + (root.readyNa > 0 ? "  \u00b7  " + root.readyNa + " n/a" : "")
                        }
                    ]

                    ReadinessChecklist {
                        Layout.fillWidth: true
                    }
                }

                ErrorCard {
                    id: errorCard
                    objectName: "run.errorCard"
                }

                AppCard {
                    objectName: "run.progressCard"
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

                            StatusMark {
                                status: appBridge.resultStrictState === "fail" ? "error" : "ok"
                            }
                            Label {
                                Layout.fillWidth: true
                                text: appBridge.outputPathResolved
                                color: Theme.text
                                font.pixelSize: Theme.fontSmall
                                elide: Text.ElideMiddle
                                ToolTip.visible: outPathHover.hovered
                                ToolTip.delay: 500
                                ToolTip.text: appBridge.outputPathResolved
                                HoverHandler { id: outPathHover }
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

    // --- File dialogs -----------------------------------------------------
    // Both start where the user already is instead of at the app folder.
    FileDialog {
        id: inputFileMenu
        currentFolder: appBridge.folderUrl(appBridge.lastInputDir)
        nameFilters: ["Media files (*.mp4 *.mkv *.webm *.mov *.avi *.mp3 *.m4a *.wav *.flac *.ogg)", "All files (*)"]
        onAccepted: appBridge.filePath = appBridge.localPath(selectedFile)
    }

    FileDialog {
        id: outputFileMenu
        fileMode: FileDialog.SaveFile
        currentFolder: appBridge.folderUrl(appBridge.lastInputDir)
        currentFile: appBridge.fileUrl(appBridge.outPath)
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
        onAccepted: appBridge.glossaryPath = appBridge.localPath(selectedFile)
    }
}
