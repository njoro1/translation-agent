import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Filter chip with an optional count. Selected state fills with the text colour
// so it is legible in both themes (the mockup's "on" state).
Button {
    id: root

    property string count: ""
    property string iconName: ""

    checkable: true
    implicitHeight: 28
    implicitWidth: contentItem.implicitWidth + 24
    padding: 0

    background: Rectangle {
        radius: 999
        color: root.checked ? Theme.text : (root.hovered ? Theme.surfaceAlt : "transparent")
        border.width: root.checked ? 0 : 1
        border.color: Theme.border
    }

    contentItem: RowLayout {
        spacing: 6

        Icon {
            visible: root.iconName !== ""
            name: root.iconName
            color: root.checked ? Theme.background : Theme.textDim
            Layout.preferredWidth: 12
            Layout.preferredHeight: 12
        }

        Label {
            text: root.text
            color: root.checked ? Theme.background : Theme.textDim
            font.pixelSize: Theme.fontSmall
            font.bold: root.checked
        }

        Label {
            visible: root.count !== ""
            text: root.count
            color: root.checked ? Theme.background : Theme.textMuted
            font.pixelSize: Theme.fontTiny
            font.family: Theme.monoFont
            opacity: 0.8
        }
    }

    Accessible.role: Accessible.Button
    Accessible.name: root.text
    Accessible.checkable: true
    Accessible.checked: root.checked
}
