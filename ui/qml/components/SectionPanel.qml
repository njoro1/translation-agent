import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Rectangle {
    id: root

    default property alias content: contentLayout.data
    property string title: ""

    color: Theme.surface
    radius: Theme.radiusMd
    border.color: Theme.border
    border.width: 1
    implicitHeight: contentLayout.implicitHeight + (title !== "" ? 34 : 16)

    ColumnLayout {
        id: contentLayout
        anchors.fill: parent
        anchors.margins: 12
        spacing: Theme.sm

        FieldLabel {
            visible: root.title !== ""
            text: root.title.toUpperCase()
        }
    }
}
