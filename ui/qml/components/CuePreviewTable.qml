import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Virtualized cue review table backed by CueResultModel + filter proxy.
// Never a giant TextArea: only visible rows are instantiated.
ColumnLayout {
    id: root

    spacing: Theme.sm

    readonly property var proxy: appBridge.cueProxy

    function _copyRow(row) {
        const d = proxy.get(row)
        if (d && d.text)
            clipboardHelper.setText(d.index + "\n" + d.source + "\n=> " + d.text)
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
                    { id: "failed", label: "Failed" },
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
                        text: parent.modelData.label
                        color: parent.checked ? "#FFFFFF" : Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        TextField {
            id: searchField
            Layout.preferredWidth: 240
            placeholderText: "Search source or translationâ€¦"
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
        }

        Item { Layout.fillWidth: true }

        Label {
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
            text: listView.count + " cue(s)"
        }
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
            Label { text: "Status"; Layout.preferredWidth: 90; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
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
        ScrollBar.vertical: ScrollBar {}

        delegate: Rectangle {
            width: listView.width
            height: Math.max(30, rowLayout.implicitHeight + 10)
            radius: Theme.radiusSm
            color: {
                if (listMouse.containsMouse) return Theme.surfaceAlt
                if (statusText === "untranslated" || statusText === "empty")
                    return Theme.errorTint
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
                    maximumLineCount: 2
                    wrapMode: Text.NoWrap
                }
                Label {
                    text: (model.translationText || "").replace(/\\N/g, " ").replace(/\n/g, " ")
                    Layout.fillWidth: true
                    color: Theme.text
                    font.pixelSize: Theme.fontBody
                    elide: Text.ElideRight
                    maximumLineCount: 2
                    wrapMode: Text.NoWrap
                }
                Rectangle {
                    Layout.preferredWidth: 86
                    implicitHeight: 20
                    radius: 999
                    color: {
                        if (model.statusText === "untranslated" || model.statusText === "empty")
                            return Theme.errorTint
                        if (model.statusText === "warning") return Theme.warningTint
                        return Theme.successTint
                    }

                    Label {
                        anchors.centerIn: parent
                        text: model.statusText
                        color: {
                            if (model.statusText === "untranslated" || model.statusText === "empty")
                                return Theme.error
                            if (model.statusText === "warning") return Theme.warning
                            return Theme.success
                        }
                        font.pixelSize: 10
                        font.bold: true
                    }
                }
            }

            HoverHandler { id: listMouse }

            TapHandler {
                onDoubleTapped: root._copyRow(index)
            }
        }

        Text {
            anchors.centerIn: parent
            visible: listView.count === 0
            text: appBridge.resultReady ? "No cues match the current filter." : "Run a translation to review its cues here."
            color: Theme.textMuted
            font.pixelSize: Theme.fontLabel
        }
    }

    Label {
        text: "Double-click a row to copy it."
        color: Theme.textMuted
        font.pixelSize: Theme.fontSmall
    }

    TextEdit {
        id: clipboardHelper
        visible: false
        width: 0
        height: 0
    }
}
