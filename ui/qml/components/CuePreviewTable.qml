import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."

// Virtualized cue review table backed by CueResultModel + filter proxy.
// Never a giant TextArea: only visible rows are instantiated.
//
// Rewritten for the UX review (S-01 / S-11): the translation is now editable
// inline, a "Save subtitles" action writes the (possibly edited) cues back out,
// find/replace works across the whole set, the counter reads "Showing X of Y",
// and row status carries an icon + word (not colour alone).
ColumnLayout {
    id: root

    spacing: Theme.sm

    readonly property var proxy: appBridge.cueProxy
    property int editingIndex: -1
    property int flashIndex: -1

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

    function _copyRow(row) {
        const d = proxy.get(row)
        if (d && d.text)
            clipboardHelper.setText(d.index + "\n" + d.source + "\n=> " + d.text)
    }

    // Quality -> Review jump: scroll to and flash the requested cue.
    Connections {
        target: appBridge
        function onFocusCueIndexChanged() {
            const idx = appBridge.focusCueIndex
            if (idx >= 0 && idx < listView.count) {
                listView.positionViewAtIndex(idx, ListView.Center)
                root.flashIndex = idx
                flashTimer.restart()
            }
        }
    }

    Timer {
        id: flashTimer
        interval: 1200
        repeat: false
        onTriggered: root.flashIndex = -1
    }

    // Toolbar
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.sm

        RowLayout {
            spacing: 0

            Repeater {
                model: [
                    { id: "all", label: "All" },
                    { id: "errors", label: "Errors" },
                    { id: "failed", label: "Untranslated" },
                    { id: "warnings", label: "Warnings" }
                ]

                delegate: Button {
                    required property var modelData
                    checkable: true
                    checked: root.proxy.filterMode === modelData.id
                    implicitHeight: 28
                    onClicked: root.proxy.filterMode = modelData.id

                    background: Rectangle {
                        color: parent.checked ? Theme.accent : Theme.surfaceAlt
                        radius: Theme.radiusSm
                        border.color: Theme.border
                    }
                    contentItem: Label {
                        text: modelData.label
                        color: parent.checked ? Theme.accentText : Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    Accessible.name: "Filter: " + modelData.label
                    Accessible.role: Accessible.Button
                }
            }
        }

        TextField {
            id: searchField
            Layout.preferredWidth: 220
            placeholderText: "Search source or translation"
            font.pixelSize: Theme.fontSmall
            color: Theme.text
            onTextChanged: root.proxy.searchText = text

            background: Rectangle {
                radius: Theme.radiusSm
                color: Theme.surfaceAlt
                border.color: searchField.activeFocus ? Theme.accent : Theme.border
            }

            Image {
                visible: searchField.text !== ""
                anchors.right: parent.right
                anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                source: "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12'><text x='1' y='10' fill='%238A94A3' font-size='11'>x</text></svg>"
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: searchField.text = ""
                }
            }

            Accessible.name: "Search cues"
            Accessible.role: Accessible.EditableText
        }

        Label {
            Layout.preferredWidth: 150
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
            text: "Showing " + listView.count + " of " + appBridge.qualityTotalCues + " cues"
        }

        Item { Layout.fillWidth: true }

        Button {
            text: "Save subtitles"
            enabled: appBridge.cueEditedCount > 0
            onClicked: appBridge.saveEditedSubtitlesToDefault()

            background: Rectangle {
                radius: Theme.radiusSm
                color: parent.enabled ? (parent.hovered ? Theme.accentHover : Theme.accent) : Theme.surfaceAlt
            }
            contentItem: Label {
                text: parent.text
                color: parent.enabled ? Theme.accentText : Theme.textMuted
                font.pixelSize: Theme.fontSmall
                font.bold: true
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }

            Accessible.name: "Save edited subtitles"
            Accessible.role: Accessible.Button
        }

        Button {
            text: "\u25BE"
            implicitWidth: 30
            onClicked: actionMenu.open()

            background: Rectangle {
                radius: Theme.radiusSm
                color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                border.color: Theme.border
            }
            contentItem: Label { text: parent.text; color: Theme.text; horizontalAlignment: Text.AlignHCenter }

            Menu {
                id: actionMenu
                MenuItem { text: "Save as..."; onTriggered: saveDialog.open() }
                MenuItem { text: "Re-check quality"; onTriggered: appBridge.recheckQuality() }
                MenuItem { text: "Revert all edits"; onTriggered: appBridge.revertAllEdits() }
                MenuItem { text: "Open in external editor"; onTriggered: appBridge.openInExternalEditor() }
                MenuItem { text: "Find / replace..."; onTriggered: findRepl.visible = !findRepl.visible }
            }

            Accessible.name: "More actions"
            Accessible.role: Accessible.Button
        }

        FileDialog {
            id: saveDialog
            fileMode: FileDialog.SaveFile
            nameFilters: ["Subtitles (*.srt *.ass)"]
            onAccepted: {
                const p = appBridge.localPath(selectedFile)
                appBridge.saveEditedSubtitles(p)
            }
        }
    }

    // Find / replace disclosure
    RowLayout {
        id: findRepl
        visible: false
        Layout.fillWidth: true
        spacing: Theme.sm

        TextField {
            id: findField
            Layout.fillWidth: true
            placeholderText: "Find"
            font.pixelSize: Theme.fontSmall
            color: Theme.text
            background: Rectangle { radius: Theme.radiusSm; color: Theme.surfaceAlt; border.color: findField.activeFocus ? Theme.accent : Theme.border }
        }
        TextField {
            id: replField
            Layout.fillWidth: true
            placeholderText: "Replace"
            font.pixelSize: Theme.fontSmall
            color: Theme.text
            background: Rectangle { radius: Theme.radiusSm; color: Theme.surfaceAlt; border.color: replField.activeFocus ? Theme.accent : Theme.border }
        }
        CheckBox {
            id: regexBox
            text: "Regex"
            contentItem: Label { text: "Regex"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
        }
        Button {
            text: "Replace all"
            onClicked: {
                const n = appBridge.replaceInCues(findField.text, replField.text, regexBox.checked)
                statusBar.text = n + " replacement(s) made."
            }
            background: Rectangle {
                radius: Theme.radiusSm
                color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                border.color: Theme.border
            }
            contentItem: Label { text: parent.text; color: Theme.text; font.pixelSize: Theme.fontSmall; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        }
        Label { id: statusBar; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
    }

    // Header row
    Rectangle {
        Layout.fillWidth: true
        implicitHeight: 26
        color: Theme.surfaceAlt
        radius: Theme.radiusSm

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.sm
            anchors.rightMargin: Theme.sm
            spacing: Theme.sm

            Label { text: "#"; Layout.preferredWidth: 36; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
            Label { text: "Start"; Layout.preferredWidth: 84; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
            Label { text: "End"; Layout.preferredWidth: 84; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
            Label { text: "Source"; Layout.fillWidth: true; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
            Label { text: "Translation"; Layout.fillWidth: true; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
            Label { text: "Status"; Layout.preferredWidth: 96; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
        }
    }

    // Rows
    ListView {
        id: listView
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: root.proxy
        spacing: 1
        boundsBehavior: Flickable.StopAtBounds
        currentIndex: -1
        keyNavigationEnabled: true
        focus: true
        ScrollBar.vertical: ScrollBar {}

        delegate: Rectangle {
            id: row
            width: listView.width
            height: Math.max(Theme.rowHeight, rowLayout.implicitHeight + 10)
            radius: Theme.radiusSm
            color: {
                if (root.flashIndex === index) return Theme.accentTint
                if (listView.currentIndex === index) return Theme.surfaceAlt
                if (statusText === "untranslated" || statusText === "empty") return Theme.errorTint
                if (statusText === "warning") return Theme.warningTint
                return "transparent"
            }

            RowLayout {
                id: rowLayout
                anchors.fill: parent
                anchors.leftMargin: Theme.sm
                anchors.rightMargin: Theme.sm
                spacing: Theme.sm

                Label {
                    text: model.cueIndex
                    Layout.preferredWidth: 36
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                }
                Label {
                    text: model.startText
                    Layout.preferredWidth: 84
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                    font.family: "Consolas"
                }
                Label {
                    text: model.endText
                    Layout.preferredWidth: 84
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                    font.family: "Consolas"
                }
                Label {
                    text: model.sourceText.replace(/\n/g, " ")
                    Layout.fillWidth: true
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontBody
                    elide: Text.ElideRight
                    maximumLineCount: 3
                    wrapMode: Text.WordWrap
                    ToolTip.visible: truncated && sourceHover.hovered
                    ToolTip.delay: 400
                    ToolTip.text: model.sourceText
                    HoverHandler { id: sourceHover }
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: transField.implicitHeight + 4
                    color: (root.editingIndex === index) ? Theme.surface : "transparent"
                    radius: Theme.radiusSm
                    border.color: (root.editingIndex === index) ? Theme.accent : "transparent"

                    TextInput {
                        id: transField
                        anchors.fill: parent
                        anchors.leftMargin: 4
                        anchors.rightMargin: 4
                        text: model.translationText
                        color: model.cueEdited ? Theme.accent : Theme.text
                        font.pixelSize: Theme.fontBody
                        readOnly: root.editingIndex !== index
                        selectByMouse: true
                        verticalAlignment: TextInput.AlignVCenter
                        onAccepted: root.commitEdit(index, text)
                        onActiveFocusChanged: {
                            if (!activeFocus && root.editingIndex === index)
                                root.commitEdit(index, text)
                        }
                        Keys.onEscapePressed: { text = model.translationText; root.cancelEdit() }
                        ToolTip.visible: truncated && transHover.hovered && readOnly
                        ToolTip.delay: 400
                        ToolTip.text: model.translationText
                        HoverHandler { id: transHover }
                    }
                }
                Rectangle {
                    Layout.preferredWidth: 96
                    implicitHeight: 20
                    radius: 999
                    color: Theme.statusTint(statusText)

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 6
                        anchors.rightMargin: 6
                        spacing: 3
                        Label {
                            text: Theme.statusIcon(statusText)
                            color: Theme.statusColor(statusText)
                            font.pixelSize: 11
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

            TapHandler {
                onTapped: listView.currentIndex = index
                onDoubleTapped: { listView.currentIndex = index; root.beginEdit(index); transField.forceActiveFocus() }
            }

            Keys.onReturnPressed: { root.beginEdit(index); transField.forceActiveFocus() }
            Keys.onEnterPressed: { root.beginEdit(index); transField.forceActiveFocus() }
        }

        Keys.onUpPressed: { if (listView.currentIndex > 0) listView.currentIndex -= 1 }
        Keys.onDownPressed: { if (listView.currentIndex < listView.count - 1) listView.currentIndex += 1 }

        Text {
            anchors.centerIn: parent
            visible: listView.count === 0
            text: appBridge.resultReady ? "No cues match the current filter." : "Run a translation to review its cues here."
            color: Theme.textMuted
            font.pixelSize: Theme.fontLabel
        }
    }

    Label {
        color: Theme.textMuted
        font.pixelSize: Theme.fontSmall
        text: "Click a cue to select, double-click to edit, Ctrl+S to save."
    }

    TextEdit {
        id: clipboardHelper
        visible: false
        width: 0
        height: 0
    }

    Shortcut {
        sequence: "Ctrl+S"
        onActivated: appBridge.saveEditedSubtitlesToDefault()
    }

    Shortcut {
        sequence: "Ctrl+F"
        onActivated: { searchField.forceActiveFocus(); searchField.selectAll() }
    }
}
