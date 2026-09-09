import QtQuick
import QtQuick.Controls
import ".."

TextField {
    id: root

    // Optional human label for screen readers / test hooks.
    property string label: ""

    font.pixelSize: Theme.fontBody
    color: Theme.text
    height: Theme.fieldHeight
    selectByMouse: true
    verticalAlignment: TextInput.AlignVCenter
    placeholderTextColor: Theme.textMuted

    Accessible.role: Accessible.EditableText
    Accessible.name: root.label !== "" ? root.label : root.placeholderText
    Accessible.description: root.placeholderText

    background: Rectangle {
        implicitHeight: Theme.fieldHeight
        radius: Theme.radiusSm
        color: root.echoMode === TextInput.Password ? "#0D1117" : Theme.surfaceAlt
        border.color: root.activeFocus ? Theme.accent : Theme.border
        border.width: 1
    }
}
