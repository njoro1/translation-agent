import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// "Label ............ value" row used by the inspector / run-context cards.
RowLayout {
    id: root

    property string key: ""
    property string value: ""
    property color valueColor: Theme.text
    property bool mono: false

    spacing: 8
    Layout.fillWidth: true

    Label {
        text: root.key
        color: Theme.textMuted
        font.pixelSize: Theme.fontBody
        Layout.preferredWidth: 128
        elide: Text.ElideRight
    }

    Label {
        Layout.fillWidth: true
        text: root.value
        color: root.valueColor
        font.pixelSize: Theme.fontBody
        font.family: root.mono ? Theme.monoFont : Theme.uiFont
        horizontalAlignment: Text.AlignRight
        elide: Text.ElideMiddle
    }
}
