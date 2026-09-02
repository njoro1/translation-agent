import QtQuick
import QtQuick.Controls

Button {
    id: control

    implicitHeight: 44
    hoverEnabled: true

    // Size the button to fit its label so longer texts ("Download model & Run",
    // "Downloading model...") never overflow the background. We keep a sensible
    // minimum so short labels still look like a deliberate, tappable button.
    implicitWidth: Math.max(140, textLabel.implicitWidth + 28)

    contentItem: Label {
        id: textLabel
        text: control.text
        color: "#ffffff"
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        font.pixelSize: 14
        font.bold: true
        // Never let the label spill outside the button on the X axis; if the
        // layout ever squeezes the button narrower than its text, elide instead
        // of overflowing.
        width: control.availableWidth
        elide: Text.ElideRight
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
