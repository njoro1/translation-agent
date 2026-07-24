import QtQuick
import QtQuick.Controls

Button {
    id: control

    implicitHeight: 44
    implicitWidth: 132
    hoverEnabled: true

    contentItem: Label {
        text: control.text
        color: "#ffffff"
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        font.pixelSize: 14
        font.bold: true
    }

    background: Rectangle {
        radius: 12
        color: !control.enabled ? "#312e81"
                                 : control.down ? "#4338ca"
                                                : (control.hovered ? "#6366f1" : "#4f46e5")
        opacity: control.enabled ? 1.0 : 0.55

        Behavior on color {
            ColorAnimation { duration: 140 }
        }

        Behavior on opacity {
            NumberAnimation { duration: 140 }
        }
    }
}
