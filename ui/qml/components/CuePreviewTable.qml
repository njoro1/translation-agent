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

    // Quality -> Review jump: reveal the requested cue even when the current
    // filter would hide it.
    Connections {
        target: appBridge
        function onFocusCueIndexChanged() {
            const idx = appBridge.focusCueIndex
            if (idx < 0)
                return
            let row = root._indexForCueNumber(idx + 1)
            if (row < 0) {
                proxy.filterMode = "all"
                proxy.searchText = ""
                row = root._indexForCueNumber(idx + 1)
            }
            if (row >= 0 && row < listView.count) {
                listView.positionViewAtIndex(row, ListView.Center)
                root.flashIndex = row
                flashTimer.restart()
                root.selectRow(row)
            }
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

            AppSwitch {
                text: "Only problems"
                checked: root.proxy.filterMode === "errors"
                accessibleName: "Only show cues with problems"
                onToggled: function (checked) {
                    root.proxy.filterMode = checked ? "errors" : "all"
                }
            }

            Label {
                text: "Showing " + listView.count + " of " + appBridge.qualityTotalCues
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
                    height: 32
                    radius: Theme.radiusXs
                    color: {
                        if (root.flashIndex === index) return Theme.accentSoft
                        if (root.selectedRow === index) return Theme.surfaceRaised
                        if (statusText === "untranslated" || statusText === "empty") return Theme.errorTint
                        if (statusText === "warning") return Theme.warningTint
                        return rowHover.hovered ? Theme.surfaceAlt : "transparent"
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
                        Label {
                            text: String(model.sourceText).replace(/\n/g, " ")
                            Layout.fillWidth: true
                            color: Theme.textDim
                            font.pixelSize: Theme.fontBody
                            elide: Text.ElideRight
                            ToolTip.visible: truncated && sourceHover.hovered
                            ToolTip.delay: 400
                            ToolTip.text: model.sourceText
                            HoverHandler { id: sourceHover }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: 26
                            radius: Theme.radiusXs
                            color: (root.editingIndex === index) ? Theme.inset : "transparent"
                            border.width: (root.editingIndex === index) ? 1 : 0
                            border.color: Theme.accentLine

                            TextInput {
                                id: transField
                                anchors.fill: parent
                                anchors.leftMargin: 5
                                anchors.rightMargin: 5
                                text: model.translationText
                                color: model.cueEdited ? Theme.accent : Theme.text
                                font.pixelSize: Theme.fontBody
                                readOnly: root.editingIndex !== index
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
                                ToolTip.visible: truncated && transHover.hovered && readOnly
                                ToolTip.delay: 400
                                ToolTip.text: model.translationText
                                HoverHandler { id: transHover }
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
