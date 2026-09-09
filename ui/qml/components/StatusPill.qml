import QtQuick
import QtQuick.Controls
import ".."

Rectangle {
    id: root

    readonly property string state: appBridge.statusState
    readonly property bool running: state === "running" || state === "validating"
    // Elapsed time only makes sense while a run is active.
    readonly property bool showTimer: running && elapsedSec >= 1
    readonly property string stateText: {
        if (state === "done") return "Done"
        if (state === "failed") return "Failed"
        if (state === "cancelled") return "Cancelled"
        if (state === "validating") return "Validating"
        if (state === "running") return "Running"
        return "Ready"
    }
    property int elapsedSec: 0

    function _fmt(sec) {
        var m = Math.floor(sec / 60)
        var s = sec % 60
        return m > 0 ? m + "m " + s + "s" : s + "s"
    }

    Timer {
        running: root.running
        repeat: true
        interval: 1000
        triggeredOnStart: true
        onTriggered: root.elapsedSec = root.elapsedSec + 1
    }

    onRunningChanged: {
        if (!running)
            elapsedSec = 0
    }

    radius: 999
    implicitHeight: 26
    implicitWidth: row.implicitWidth + 22
    color: {
        if (state === "done") return Theme.successTint
        if (state === "failed") return Theme.errorTint
        if (state === "cancelled") return Theme.warningTint
        if (running) return Qt.rgba(0.24, 0.51, 0.96, 0.15)
        return Theme.surfaceAlt
    }
    border.color: {
        if (state === "done") return Theme.success
        if (state === "failed") return Theme.error
        if (state === "cancelled") return Theme.warning
        if (running) return Theme.accent
        return Theme.border
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 7

        Rectangle {
            width: 8
            height: 8
            radius: 4
            anchors.verticalCenter: parent.verticalCenter
            color: {
                if (root.state === "done") return Theme.success
                if (root.state === "failed") return Theme.error
                if (root.state === "cancelled") return Theme.warning
                if (root.running) return Theme.accent
                return Theme.textMuted
            }

            SequentialAnimation on opacity {
                running: root.running
                loops: Animation.Infinite
                NumberAnimation { to: 0.25; duration: 600 }
                NumberAnimation { to: 1.0; duration: 600 }
            }
        }

        Label {
            anchors.verticalCenter: parent.verticalCenter
            // Show the live elapsed time inside the pill (the old build
            // computed `showTimer` but never rendered it).
            text: root.showTimer
                  ? root.stateText + "  \u00B7  " + root._fmt(root.elapsedSec)
                  : root.stateText
            color: Theme.text
            font.pixelSize: Theme.fontSmall
            font.bold: true
        }
    }
}
