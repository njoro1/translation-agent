import QtQuick
import QtQuick.Controls
import ".."

// Compact text field matching the mockup's `.field` (inset background, focus
// ring). Keeps the ``label`` hook used for accessibility and test lookups.
TextField {
    id: root

    property string label: ""

    font.pixelSize: Theme.fontBody
    color: Theme.text
    height: Theme.controlHeight
    selectByMouse: true
    verticalAlignment: TextInput.AlignVCenter
    placeholderTextColor: Theme.textMuted
    leftPadding: 10
    rightPadding: 10

    Accessible.role: Accessible.EditableText
    Accessible.name: root.label !== "" ? root.label : root.placeholderText
    Accessible.description: root.placeholderText

    background: Rectangle {
        implicitHeight: Theme.controlHeight
        radius: Theme.radiusSm
        color: root.echoMode === TextInput.Password ? Theme.fieldSecretBackground : Theme.inset
        border.width: 1
        border.color: root.activeFocus ? Theme.accentLine
                                        : (root.hovered ? Theme.borderStrong : Theme.border)
    }
}
