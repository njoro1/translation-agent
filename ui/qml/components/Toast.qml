import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Transient confirmation toast (UI review 3.4).
//
// The persistent "Save" button is gone: autosave commits on its own, and this
// is the only visible confirmation. It hides itself, so it can never sit on
// screen encoding a state that has since changed — which is exactly how the
// old `● Saved` pill ended up contradicting the enabled `Save` button beside
// it.
//
// Usage: connect `appBridge.savedToast` to `show()`.
Item {
    id: root

    property string message: "Saved \u2713"
    property bool shown: false

    function show(msg) {
        if (msg !== undefined && msg !== "")
            root.message = msg
        root.shown = true
        hideTimer.restart()
    }

    function hide() { root.shown = false }

    implicitWidth: bubble.implicitWidth
    implicitHeight: bubble.implicitHeight

    opacity: root.shown ? 1 : 0
    visible: opacity > 0.01
    // `Reduce motion` must actually apply: no slide, no fade.
    Behavior on opacity { NumberAnimation { duration: Theme.reducedMotion ? 0 : 160 } }

    Timer {
        id: hideTimer
        interval: 1600
        repeat: false
        onTriggered: root.hide()
    }

    Rectangle {
        id: bubble
        implicitWidth: toastRow.implicitWidth + 22
        implicitHeight: 28
        radius: 999
        color: Theme.surfaceRaised
        border.width: 1
        border.color: Theme.toneBorder("ok")

        RowLayout {
            id: toastRow
            anchors.centerIn: parent
            spacing: 7

            Icon {
                name: "check"
                width: 13
                height: 13
                color: Theme.success
                strokeWidth: 2.4
            }

            Label {
                text: root.message
                color: Theme.text
                font.pixelSize: Theme.fontSmall
                font.bold: true
            }
        }
    }

    Accessible.role: Accessible.StaticText
    Accessible.name: root.shown ? root.message : ""
}
