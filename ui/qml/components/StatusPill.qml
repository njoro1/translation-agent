import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Run-state pill for the command bar: Ready / Validating / Running · 1m 12s /
// Done / Failed / Cancelled. Carries a word, a dot and a colour (never colour
// alone).
Rectangle {
    id: root

    readonly property string state: appBridge.statusState
    readonly property bool running: state === "running" || state === "validating"
    readonly property bool showTimer: running && elapsedSec >= 1

    readonly property string stateText: {
        if (state === "done") return "Done"
        if (state === "failed") return "Failed"
        if (state === "cancelled") return "Cancelled"
        if (state === "validating") return "Validating"
        if (state === "running") return "Running"
        return "Ready"
    }

    readonly property string tone: {
        if (state === "done") return "ok"
        if (state === "failed") return "err"
        if (state === "cancelled") return "warn"
        if (running) return "acc"
        return "mute"
    }

    property int elapsedSec: 0

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

    implicitHeight: 24
    implicitWidth: row.implicitWidth + 20
    radius: 999
    color: Theme.toneTint(root.tone)
    border.width: 1
    border.color: Theme.toneBorder(root.tone)

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 6

        Rectangle {
            Layout.preferredWidth: 6
            Layout.preferredHeight: 6
            radius: 3
            color: Theme.toneColor(root.tone)

            SequentialAnimation on opacity {
                running: root.running && !Theme.reducedMotion
                loops: Animation.Infinite
                NumberAnimation { to: 0.25; duration: 600 }
                NumberAnimation { to: 1.0; duration: 600 }
            }
        }

        Label {
            text: root.showTimer
                  ? root.stateText + "  ·  " + Theme.formatDuration(root.elapsedSec)
                  : root.stateText
            color: Theme.toneColor(root.tone)
            font.pixelSize: Theme.fontSmall
            font.bold: true
        }
    }

    Accessible.role: Accessible.StaticText
    Accessible.name: "Run status: " + root.stateText
}
