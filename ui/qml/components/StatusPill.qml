import QtQuick
import QtQuick.Controls
import ".."

Rectangle {
    id: root

    readonly property string state: appBridge.statusState
    readonly property bool running: state === "running" || state === "validating"

    radius: 999
    implicitHeight: 26
    implicitWidth: row.implicitWidth + 22
    color: {
        if (state === "done") return Theme.successTint
        if (state === "failed") return Theme.errorTint
        if (running) return Qt.rgba(0.24, 0.51, 0.96, 0.15)
        return Theme.surfaceAlt
    }
    border.color: {
        if (state === "done") return Theme.success
        if (state === "failed") return Theme.error
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
            text: {
                if (root.state === "done") return "Done"
                if (root.state === "failed") return "Failed"
                if (root.state === "validating") return "Validating"
                if (root.state === "running") return "Running"
                return "Ready"
            }
            color: Theme.text
            font.pixelSize: Theme.fontSmall
            font.bold: true
        }
    }
}
