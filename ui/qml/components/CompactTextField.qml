import QtQuick
import QtQuick.Controls
import ".."

TextField {
    id: root

    font.pixelSize: Theme.fontBody
    color: Theme.text
    height: Theme.fieldHeight
    selectByMouse: true
    verticalAlignment: TextInput.AlignVCenter
    placeholderTextColor: Theme.textMuted

    background: Rectangle {
        implicitHeight: Theme.fieldHeight
        radius: Theme.radiusSm
        color: root.echoMode === TextInput.Password ? "#0D1117" : Theme.surfaceAlt
        border.color: root.activeFocus ? Theme.accent : Theme.border
        border.width: 1
    }
}
