import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Card with an optional header band (step number + uppercase title + right-hand
// chips) and a default content slot.
//
//   AppCard {
//       title: "Source"; stepNumber: 1; active: true
//       headerExtra: [ Chip { text: "YouTube"; tone: "acc" } ]
//       ColumnLayout { ... }        // <- default content
//   }
Rectangle {
    id: root

    default property alias content: body.data
    property alias headerExtra: headerExtraRow.data

    property string title: ""
    property int stepNumber: 0
    property string note: ""
    property bool active: false
    property bool tight: false
    property int padding: tight ? Theme.md : 15

    color: Theme.surface
    radius: Theme.radiusLg
    border.color: Theme.border
    border.width: 1
    implicitHeight: outer.implicitHeight

    ColumnLayout {
        id: outer
        anchors.fill: parent
        spacing: 0

        // --- Header ---------------------------------------------------------
        Item {
            id: header
            visible: root.title !== ""
            Layout.fillWidth: true
            Layout.preferredHeight: headerRow.implicitHeight + 26

            RowLayout {
                id: headerRow
                anchors.fill: parent
                anchors.leftMargin: 15
                anchors.rightMargin: 15
                spacing: 9

                Rectangle {
                    visible: root.stepNumber > 0
                    implicitWidth: 18
                    implicitHeight: 18
                    radius: 5
                    color: root.active ? Theme.accent : Theme.surfaceRaised

                    Label {
                        anchors.centerIn: parent
                        text: String(root.stepNumber)
                        color: root.active ? Theme.accentInk : Theme.textMuted
                        font.pixelSize: Theme.fontTiny
                        font.family: Theme.monoFont
                        font.bold: true
                    }
                    Accessible.ignored: true
                }

                Label {
                    text: root.title.toUpperCase()
                    color: Theme.textDim
                    font.pixelSize: Theme.fontSmall
                    font.bold: true
                    font.letterSpacing: 0.9
                }

                Label {
                    visible: root.note !== ""
                    Layout.fillWidth: true
                    text: root.note
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                    elide: Text.ElideRight
                }

                Item {
                    visible: root.note === ""
                    Layout.fillWidth: true
                }

                RowLayout {
                    id: headerExtraRow
                    spacing: 6
                }
            }

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.borderSoft
            }
        }

        // --- Body -----------------------------------------------------------
        ColumnLayout {
            id: body
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: root.padding
            spacing: 10
        }
    }
}
