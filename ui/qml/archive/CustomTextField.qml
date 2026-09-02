import QtQuick
import QtQuick.Controls

TextField {
    id: control

    color: "#ffffff"
    selectByMouse: true
    placeholderTextColor: "#6B7280"

    background: Rectangle {
        radius: 12
        color: "#1F2430"
        border.width: 1
        border.color: control.activeFocus ? "#6C5CE7" : "#2A303C"

        Behavior on border.color {
            ColorAnimation { duration: 150 }
        }
    }
}
