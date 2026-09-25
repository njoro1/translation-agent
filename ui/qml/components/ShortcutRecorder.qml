import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Records a key combination for the shortcut remap editor (UI review 5.5).
//
// A read-only shortcut list under "Settings" is decoration. This is the piece
// that makes the category real: click Record, press a combo, and the bridge
// persists it. Escape cancels, Backspace clears.
Item {
    id: root

    property bool recording: false
    property string label: ""

    signal recorded(string sequence)

    implicitWidth: captureLabel.implicitWidth + 24
    implicitHeight: Theme.controlHeightSmall

    function startRecording() {
        root.recording = true
        root.forceActiveFocus()
    }

    focus: root.recording
    activeFocusOnTab: false

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusXs
        color: root.recording ? Theme.accentSoft : Theme.surfaceRaised
        border.width: 1
        border.color: root.recording ? Theme.accentLine : Theme.border

        Label {
            id: captureLabel
            anchors.centerIn: parent
            text: root.recording ? "Press a combination\u2026" : (root.label || "Record")
            color: root.recording ? Theme.accent : Theme.textDim
            font.pixelSize: Theme.fontSmall
            font.family: Theme.monoFont
        }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.startRecording()
    }

    // The recorder only listens while armed, so it cannot swallow keys the rest
    // of the app needs.
    Keys.onPressed: (event) => {
        if (!root.recording) {
            event.accepted = false
            return
        }
        event.accepted = true
        if (event.key === Qt.Key_Escape) {
            root.recording = false
            return
        }
        if (event.key === Qt.Key_Backspace) {
            root.recorded("")
            root.recording = false
            return
        }

        var parts = []
        if (event.modifiers & Qt.ControlModifier) parts.push("Ctrl")
        if (event.modifiers & Qt.AltModifier) parts.push("Alt")
        if (event.modifiers & Qt.ShiftModifier) parts.push("Shift")

        var key = ""
        if (event.key >= Qt.Key_F1 && event.key <= Qt.Key_F35) {
            key = "F" + (event.key - Qt.Key_F1 + 1)
        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            key = "Return"
        } else if (event.key === Qt.Key_Delete) {
            key = "Del"
        } else if (event.key === Qt.Key_Space) {
            key = "Space"
        } else if (event.key === Qt.Key_Tab) {
            key = "Tab"
        } else if (event.text !== "" && event.text.charCodeAt(0) > 32) {
            key = event.text.toUpperCase()
        }

        if (key === "") {
            // Modifier-only press: stay armed and wait for the real key.
            return
        }
        root.recorded(parts.concat([key]).join("+"))
        root.recording = false
    }

    onRecordingChanged: {
        if (recording)
            root.forceActiveFocus()
    }

    Accessible.role: Accessible.Button
    Accessible.name: root.recording ? "Recording a shortcut, press a key combination"
                                    : "Record a new shortcut"
}
