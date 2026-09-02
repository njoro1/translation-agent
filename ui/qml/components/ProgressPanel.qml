import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

ColumnLayout {
    id: root

    spacing: Theme.xs

    Label {
        text: {
            if (!appBridge.isRunning && appBridge.statusState === "done") return "Completed"
            if (appBridge.progressStage !== "")
                return appBridge.progressStage.charAt(0).toUpperCase()
                    + appBridge.progressStage.slice(1)
            return "Idle"
        }
        color: Theme.textMuted
        font.pixelSize: Theme.fontSmall
    }

    ProgressBar {
        id: bar
        Layout.fillWidth: true
        from: 0
        to: appBridge.progressTotal > 0 ? appBridge.progressTotal : 1
        value: appBridge.progressDone
        indeterminate: appBridge.isRunning && appBridge.progressTotal <= 0

        background: Rectangle {
            implicitHeight: 6
            radius: 3
            color: Theme.surfaceAlt
        }
        contentItem: Item {
            implicitHeight: 6
            Rectangle {
                width: bar.visualPosition * parent.width
                height: parent.height
                radius: 3
                color: Theme.accent
                visible: !bar.indeterminate
            }
            Rectangle {
                width: parent.width / 3
                height: parent.height
                radius: 3
                color: Theme.accent
                visible: bar.indeterminate
                XAnimator on x {
                    running: bar.indeterminate
                    from: 0
                    to: bar.width - width
                    loops: Animation.Infinite
                    duration: 900
                }
            }
        }
    }

    Label {
        visible: appBridge.progressTotal > 0
        text: appBridge.progressDone + " / " + appBridge.progressTotal
        color: Theme.textMuted
        font.pixelSize: Theme.fontSmall
    }
}
