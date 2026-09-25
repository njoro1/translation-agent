import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."

// Virtualized cue review table backed by CueResultModel + filter proxy.
// Never a giant TextArea: only visible rows are instantiated.
//
// Filter chips drive the proxy's All / OK / Warnings / Failed modes, the search
// box drives its case-insensitive text search, and a row click drives the cue
// inspector (master-detail). Editing writes straight into the model, so the
// Save / Re-check / Revert actions operate on the edited set.
Item {
    id: root

    property int editingIndex: -1
    property int flashIndex: -1
    property int selectedRow: -1

    signal rowSelected(int row)

    readonly property var proxy: appBridge.cueProxy
    readonly property var counts: appBridge.cueCounts
    readonly property int count: listView.count

    // Spelled out next to the row count so the count is never ambiguous about
    // *what* it is counting.
    readonly property string filterName: {
        const mode = root.proxy.filterMode
        if (mode === "ok") return "OK only"
        if (mode === "warnings") return "warnings only"
        if (mode === "failed") return "failed only"
        if (mode === "errors") return "problems only"
        return ""
    }

    implicitHeight: layout.implicitHeight

    // Step the selection by ``delta`` rows (drives the cue inspector's
    // Previous / Next buttons and the arrow keys).
    function step(delta) {
        if (listView.count === 0)
            return
        const next = Math.max(0, Math.min(listView.count - 1, root.selectedRow + delta))
        listView.positionViewAtIndex(next, ListView.Contain)
        root.selectRow(next)
    }

    // Expand the ASS line separator for display.
    //
    // `src/postprocess.py::break_lines` emits a literal `\N`, and only the
    // writers normalise it: the SRT writer converts it to a real newline
    // (`translate.py:637`) and the ASS writer converts a real newline back to
    // `\N` (`ass_io.py:161`). Both forms are therefore valid in the store, and
    // the result JSON keeps whichever one the pipeline produced — so a wrapped
    // cue printed "first line\Nsecond line" as one visible line in the table.
    //
    // This is a *rendering* helper only. `transField` still receives the raw
    // text so an edit round-trips byte-for-byte.
    function displayText(raw) {
        return String(raw === undefined || raw === null ? "" : raw).replace(/\\N/g, "\n")
    }

    function beginEdit(row) {
        root.editingIndex = row
    }

    function commitEdit(row, text) {
        proxy.setData(proxy.index(row, 0), text)
        root.editingIndex = -1
    }

    function cancelEdit() {
        root.editingIndex = -1
    }

    // Ctrl+F lives on the window (Main.qml) so it works from every page; this
    // is the page-side half of it.
    function focusSearch() {
        searchField.forceActiveFocus()
        searchField.selectAll()
    }

    function _copyRow(row) {
        const d = proxy.get(row)
        if (d && d.text)
            appBridge.copyToClipboard(d.index + "\n" + d.source + "\n=> " + d.text)
    }

    function selectRow(row) {
        root.selectedRow = row
        listView.currentIndex = row
        root.rowSelected(row)
    }

    function _indexForCueNumber(cueNumber) {
        const target = Math.max(1, cueNumber)
        for (let i = 0; i < listView.count; i++) {
            const d = proxy.get(i)
            if (d && d.index === target)
                return i
        }
        return -1
    }

    // Quality -> Review and Timeline -> Review jump: reveal the requested cue
    // even when the current filter would hide it.
    function selectCue(cueNumber) {
        const target = Math.max(1, cueNumber)
        let row = root._indexForCueNumber(target)
        if (row < 0) {
            root.proxy.filterMode = "all"
            root.proxy.searchText = ""
            root.proxy.clearCueRange()
            row = root._indexForCueNumber(target)
        }
        if (row >= 0 && row < listView.count) {
            listView.positionViewAtIndex(row, ListView.Center)
            root.flashIndex = row
            flashTimer.restart()
            root.selectRow(row)
        }
    }

    function filterToCueRange(first, last) {
        root.proxy.setCueRange(first, last)
    }

    function clearCueRange() {
        root.proxy.clearCueRange()
    }

    // Quality -> Review jump.
    Connections {
        target: appBridge
        function onFocusCueIndexChanged() {
            const idx = appBridge.focusCueIndex
            if (idx < 0)
                return
            root.selectCue(idx + 1)
        }
    }

    Timer {
        id: flashTimer
        interval: 1200
        repeat: false
        onTriggered: root.flashIndex = -1
    }

    ColumnLayout {
        id: layout
        anchors.fill: parent
        spacing: Theme.sm

        // --- Filter / search bar ------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            FilterChip {
                text: "All"
                count: String(root.counts.total)
                checked: root.proxy.filterMode === "all"
                onClicked: root.proxy.filterMode = "all"
            }
            FilterChip {
                text: "OK"
                iconName: "check"
                count: String(root.counts.ok)
                checked: root.proxy.filterMode === "ok"
                onClicked: root.proxy.filterMode = "ok"
            }
            FilterChip {
                text: "Warnings"
                iconName: "alert"
                count: String(root.counts.warnings)
                checked: root.proxy.filterMode === "warnings"
                onClicked: root.proxy.filterMode = "warnings"
            }
            FilterChip {
                text: "Failed"
                iconName: "x"
                count: String(root.counts.failed)
                checked: root.proxy.filterMode === "failed"
                onClicked: root.proxy.filterMode = "failed"
            }

            Rectangle {
                implicitWidth: 1
                implicitHeight: 20
                color: Theme.border
            }

            CompactTextField {
                id: searchField
                Layout.preferredWidth: 220
                height: Theme.controlHeightSmall
                placeholderText: "Search source or translation…"
                label: "Search cues"
                onTextChanged: root.proxy.searchText = text
            }

            Item { Layout.fillWidth: true }

            // The timeline drag sets a cue range; it has to be visible and
            // removable from here, or the table silently shows a subset
            // (UI review 5.3).
            Chip {
                objectName: "cues.rangeChip"
                visible: root.proxy.hasCueRange
                text: root.proxy.cueRangeLabel
                tone: "acc"
                mono: true
            }
            AppButton {
                objectName: "cues.clearRange"
                visible: root.proxy.hasCueRange
                text: "Clear range"
                small: true
                variant: "ghost"
                iconName: "x"
                onClicked: root.clearCueRange()
            }

            // The "Only problems" switch is gone. It wrote the same
            // `proxy.filterMode` the four chips above own, so it could silently
            // disagree with them — the chips would still show "All" selected
            // while the table showed errors. Two editors, one store, no
            // reconciliation (UI review 1.2 / T-5.2).
            Label {
                objectName: "cues.showingCount"
                text: "Showing " + listView.count + " of " + appBridge.qualityTotalCues
                      + (root.proxy.filterMode === "all" ? "" : " \u00b7 " + root.filterName)
                color: Theme.textMuted
                font.pixelSize: Theme.fontSmall
            }

            AppButton {
                text: "Export"
                small: true
                variant: "ghost"
                iconName: "download"
                enabled: appBridge.resultReady
                onClicked: saveDialog.open()
                Accessible.name: "Export the edited subtitles"
            }
        }

        // --- Header row ---------------------------------------------------
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 30
            radius: Theme.radiusSm
            color: Theme.surfaceAlt

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 8

                Label { text: "#"; Layout.preferredWidth: 40; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                Label { text: "START"; Layout.preferredWidth: 88; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                Label { text: "END"; Layout.preferredWidth: 88; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                Label { text: "SOURCE"; Layout.fillWidth: true; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                Label { text: "TRANSLATION"; Layout.fillWidth: true; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                Label { text: "STATUS"; Layout.preferredWidth: 84; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
            }
        }

        // --- Rows ---------------------------------------------------------
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 120

            ListView {
                id: listView
                anchors.fill: parent
                clip: true
                model: root.proxy
                spacing: 1
                boundsBehavior: Flickable.StopAtBounds
                currentIndex: -1
                keyNavigationEnabled: true
                focus: true
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Rectangle {
                    id: row
                    width: listView.width
                    height: 38
                    radius: Theme.radiusXs
                    // Severity is not allowed to live in the row's *fill*:
                    // tinting the background under body copy costs contrast on
                    // every row, and it made a warning row harder to read than
                    // an OK one. It goes on the left edge instead, and the
                    // STATUS cell keeps the icon + word (§2.1 / T-5.1).
                    color: {
                        if (root.flashIndex === index) return Theme.accentSoft
                        if (root.selectedRow === index) return Theme.surfaceRaised
                        return rowHover.hovered ? Theme.surfaceAlt : "transparent"
                    }

                    Rectangle {
                        objectName: "cueRow.severityBar"
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        width: 3
                        height: parent.height - 10
                        radius: 1.5
                        color: statusText === "ok" ? "transparent"
                                                   : Theme.statusColor(statusText)
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 8

                        Label {
                            text: model.cueIndex
                            Layout.preferredWidth: 40
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontTiny
                            font.family: Theme.monoFont
                        }
                        Label {
                            text: model.startText
                            Layout.preferredWidth: 88
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontTiny
                            font.family: Theme.monoFont
                        }
                        Label {
                            text: model.endText
                            Layout.preferredWidth: 88
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontTiny
                            font.family: Theme.monoFont
                        }

                        // Source and translation both wrap to two lines in-cell
                        // and elide past that, full text on hover. A two-line
                        // cue is the common case, and clipping it to one line
                        // hid the half that carried the meaning (T-5.1).
                        Text {
                            Layout.fillWidth: true
                            text: String(model.sourceText).replace(/\n/g, " ")
                            color: Theme.textDim
                            font.pixelSize: Theme.fontBody
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            verticalAlignment: Text.AlignVCenter
                            ToolTip.visible: truncated && sourceHover.hovered
                            ToolTip.delay: 400
                            ToolTip.text: model.sourceText
                            HoverHandler { id: sourceHover }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: parent.height - 10
                            radius: Theme.radiusXs
                            color: (root.editingIndex === index) ? Theme.inset : "transparent"
                            border.width: (root.editingIndex === index) ? 1 : 0
                            border.color: Theme.accentLine

                            // Read mode is a wrapping Text, not a read-only
                            // TextInput: a TextInput is single-line by
                            // construction, which is why translations clipped.
                            Text {
                                id: transLabel
                                anchors.fill: parent
                                anchors.leftMargin: 5
                                anchors.rightMargin: 5
                                visible: root.editingIndex !== index
                                text: root.displayText(model.translationText)
                                color: model.cueEdited ? Theme.accent : Theme.text
                                font.pixelSize: Theme.fontBody
                                wrapMode: Text.WordWrap
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                verticalAlignment: Text.AlignVCenter
                                ToolTip.visible: truncated && transHover.hovered
                                ToolTip.delay: 400
                                ToolTip.text: root.displayText(model.translationText)
                                HoverHandler { id: transHover }
                            }

                            TextInput {
                                id: transField
                                anchors.fill: parent
                                anchors.leftMargin: 5
                                anchors.rightMargin: 5
                                visible: root.editingIndex === index
                                text: model.translationText
                                color: Theme.accent
                                font.pixelSize: Theme.fontBody
                                selectByMouse: true
                                verticalAlignment: TextInput.AlignVCenter
                                clip: true
                                onAccepted: root.commitEdit(index, text)
                                onActiveFocusChanged: {
                                    if (!activeFocus && root.editingIndex === index)
                                        root.commitEdit(index, text)
                                }
                                Keys.onEscapePressed: {
                                    text = model.translationText
                                    root.cancelEdit()
                                }
                            }
                        }

                        Rectangle {
                            Layout.preferredWidth: 84
                            implicitHeight: 20
                            radius: 999
                            color: Theme.statusTint(statusText)

                            RowLayout {
                                anchors.centerIn: parent
                                spacing: 4

                                Label {
                                    text: Theme.statusIcon(statusText)
                                    color: Theme.statusColor(statusText)
                                    font.pixelSize: 10
                                    font.bold: true
                                }
                                Label {
                                    text: Theme.statusLabel(statusText)
                                    color: Theme.statusColor(statusText)
                                    font.pixelSize: 10
                                    font.bold: true
                                }
                            }

                            Accessible.role: Accessible.Indicator
                            Accessible.name: "Cue status: " + Theme.statusLabel(statusText)
                        }
                    }

                    HoverHandler { id: rowHover }

                    TapHandler {
                        onTapped: root.selectRow(index)
                        onDoubleTapped: {
                            root.selectRow(index)
                            root.beginEdit(index)
                            transField.forceActiveFocus()
                        }
                    }

                    Keys.onReturnPressed: {
                        root.beginEdit(index)
                        transField.forceActiveFocus()
                    }
                    Keys.onEnterPressed: {
                        root.beginEdit(index)
                        transField.forceActiveFocus()
                    }
                }

                Keys.onUpPressed: {
                    if (listView.currentIndex > 0)
                        root.selectRow(listView.currentIndex - 1)
                }
                Keys.onDownPressed: {
                    if (listView.currentIndex < listView.count - 1)
                        root.selectRow(listView.currentIndex + 1)
                }

                Text {
                    anchors.centerIn: parent
                    width: parent.width - 40
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                    visible: listView.count === 0
                    text: appBridge.resultReady
                          ? "No cues match the current filter."
                          : "Run a translation to review its cues here."
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontLabel
                }
            }
        }
    }

    FileDialog {
        id: saveDialog
        fileMode: FileDialog.SaveFile
        nameFilters: ["Subtitles (*.srt *.ass)"]
        onAccepted: appBridge.saveEditedSubtitles(appBridge.localPath(selectedFile))
    }

    TextEdit {
        id: clipboardHelper
        visible: false
        width: 0
        height: 0
    }
}
