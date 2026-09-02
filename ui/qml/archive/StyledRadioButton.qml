import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RadioButton {
    id: control

    property var buttonGroup: null

    indicator: Rectangle {
        implicitWidth: 18
        implicitHeight: 18
        x: control.leftPadding
        y: parent.height / 2 - height / 2
        radius: 9
        border.color: control.checked ? "#6366F1" : "#4B5563"
        border.width: control.checked ? 2 : 1
        color: "transparent"

        Rectangle {
            width: 8
            height: 8
            x: 5
            y: 5
            radius: 4
            color: "#6366F1"
            visible: control.checked

            Behavior on visible {
                NumberAnimation { duration: 100 }
            }
        }
    }

    contentItem: Text {
        text: control.text
        font: control.font
        opacity: enabled ? 1.0 : 0.3
        color: "#E5E7EB"
        verticalAlignment: Text.AlignVCenter
        leftPadding: control.indicator.width + 8
    }
}