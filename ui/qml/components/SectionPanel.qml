import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Rectangle {
    id: root

    // The body content is whatever children the using panel declares.
    default property alias content: body.data
    property string title: ""
    property bool expanded: true

    color: Theme.surface
    radius: Theme.radiusMd
    border.color: Theme.border
    border.width: 1

    ColumnLayout {
        id: outer
        anchors.fill: parent
        anchors.margins: 12
        spacing: Theme.sm

        // Header band (always visible, toggles collapse when there is a title).
        //
        // The click target wraps the layout instead of living inside it:
        // ``anchors.fill`` on a child of a *Layout* is undefined behaviour
        // (Qt warned "Detected anchors on an item that is managed by a layout").
        Item {
            visible: root.title !== ""
            Layout.fillWidth: true
            Layout.preferredHeight: header.implicitHeight

            RowLayout {
                id: header
                anchors.fill: parent
                spacing: Theme.sm

                Label {
                    text: root.expanded ? "\u25BC" : "\u25B6"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                }
                FieldLabel {
                    Layout.fillWidth: true
                    text: root.title.toUpperCase()
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.expanded = !root.expanded

                Accessible.role: Accessible.Button
                Accessible.name: root.title + (root.expanded ? ", expanded" : ", collapsed")
            }
        }

        // Body (collapsible).
        ColumnLayout {
            id: body
            visible: root.expanded
            Layout.fillWidth: true
            spacing: Theme.sm
        }
    }

    implicitHeight: outer.implicitHeight + 24
}
