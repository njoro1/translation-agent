import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

ColumnLayout {
    id: root

    spacing: Theme.xs

    function _fmt(sec) {
        var s = Math.max(0, Math.floor(sec))
        var m = Math.floor(s / 60)
        var rs = s % 60
        return (m > 0 ? m + "m " : "") + rs + "s"
    }

    // Live values polled from the bridge once per second so elapsed/ETA tick
    // even when no progress event arrives (S-07).
    property int _liveElapsed: appBridge.currentStageElapsed
    property int _liveEta: appBridge.estimatedRemainingSec
    property int _runElapsed: appBridge.runElapsedSec
    property real startedAt: NaN

    Connections {
        target: appBridge
        function onIsRunningChanged() {
            if (appBridge.isRunning) {
                root.startedAt = Date.now()
                root.timer.restart()
            } else {
                root.timer.stop()
                root._liveElapsed = appBridge.currentStageElapsed
                root._liveEta = appBridge.estimatedRemainingSec
                root._runElapsed = appBridge.runElapsedSec
            }
        }
    }

    Timer {
        id: timer
        interval: 1000
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            root._liveElapsed = appBridge.currentStageElapsed
            root._liveEta = appBridge.estimatedRemainingSec
            root._runElapsed = appBridge.runElapsedSec
        }
    }

    readonly property string statusLine: {
        if (appBridge.isRunning)
            return appBridge.statusMessage
        if (appBridge.statusState === "done" || appBridge.statusState === "failed")
            return appBridge.statusMessage
        return ""
    }

    Label {
        Layout.fillWidth: true
        visible: root.statusLine !== ""
        text: root.statusLine
        color: appBridge.statusState === "failed" ? Theme.error
             : appBridge.statusState === "cancelled" ? Theme.warning
             : Theme.text
        font.pixelSize: Theme.fontSmall
        elide: Text.ElideMiddle
    }

    // Named stage strip (S-07): each pipeline phase with its elapsed time.
    ListView {
        id: stageStrip
        Layout.fillWidth: true
        visible: appBridge.stageList.length > 0
        height: visible ? contentHeight : 0
        spacing: Theme.xs
        interactive: false
        model: appBridge.stageList

        delegate: RowLayout {
            width: stageStrip.width
            spacing: Theme.sm
            property bool isCurrent: index === appBridge.stageList.length - 1 && appBridge.isRunning

            Label {
                text: (isCurrent ? "\u25B6 " : "\u2713 ") + modelData.label
                color: isCurrent ? Theme.text : Theme.textMuted
                font.pixelSize: Theme.fontSmall
                font.bold: isCurrent
            }
            Item { Layout.fillWidth: true }
            Label {
                text: root._fmt(isCurrent ? root._liveElapsed : modelData.elapsed)
                color: Theme.textMuted
                font.pixelSize: Theme.fontSmall
            }

            Accessible.role: Accessible.ListItem
            Accessible.name: modelData.label
                + (isCurrent ? ", in progress, " + root._fmt(root._liveElapsed) + " elapsed"
                            : ", done in " + root._fmt(modelData.elapsed))
        }
    }

    Label {
        visible: appBridge.isRunning
        text: "Elapsed: " + root._fmt(root._runElapsed)
              + (root._liveEta > 0 ? "   \u00B7   ~" + root._fmt(root._liveEta) + " left" : "")
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
              + " (" + Math.round(100 * appBridge.progressDone / Math.max(appBridge.progressTotal, 1)) + "%)"
        color: Theme.textMuted
        font.pixelSize: Theme.fontSmall
    }
}
