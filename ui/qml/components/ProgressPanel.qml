import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Live run panel: progress ring + elapsed/remaining/windows tiles + stage
// stepper + a determinate bar. Live values are polled once per second so
// elapsed/ETA tick even when no progress event arrives.
ColumnLayout {
    id: root

    spacing: Theme.md

    property int _liveElapsed: appBridge.currentStageElapsed
    property int _liveEta: appBridge.estimatedRemainingSec
    property int _runElapsed: appBridge.runElapsedSec

    readonly property real fraction: appBridge.progressTotal > 0
                                     ? appBridge.progressDone / appBridge.progressTotal : 0
    readonly property int percent: Math.round(100 * fraction)
    readonly property int windowCount: appBridge.stageList.length
    readonly property string currentStageName: windowCount > 0
                                               ? appBridge.stageList[windowCount - 1].name : ""

    // `running` is declarative rather than driven by `restart()` / `stop()`
    // from a `Connections` handler. The handler could fire while this Timer had
    // not been created yet — "Cannot read property 'stop' of undefined" — which
    // stayed invisible until the window was actually shown.
    Timer {
        id: timer
        interval: 1000
        repeat: true
        triggeredOnStart: true
        running: appBridge.isRunning
        onTriggered: {
            root._liveElapsed = appBridge.currentStageElapsed
            root._liveEta = appBridge.estimatedRemainingSec
            root._runElapsed = appBridge.runElapsedSec
        }
    }

    Connections {
        target: appBridge
        function onIsRunningChanged() {
            // Freeze the readouts on the final values once the run ends.
            if (!appBridge.isRunning) {
                root._liveElapsed = appBridge.currentStageElapsed
                root._liveEta = appBridge.estimatedRemainingSec
                root._runElapsed = appBridge.runElapsedSec
            }
        }
    }

    // --- Ring + tiles ------------------------------------------------------
    RowLayout {
        Layout.fillWidth: true
        spacing: 22

        Item {
            Layout.preferredWidth: 118
            Layout.preferredHeight: 118
            Layout.alignment: Qt.AlignVCenter

            ProgressRing {
                anchors.fill: parent
                value: root.fraction
                thickness: 9
                valueColor: appBridge.statusState === "failed" ? Theme.error
                            : appBridge.statusState === "cancelled" ? Theme.warning
                            : Theme.accent
            }

            ColumnLayout {
                anchors.centerIn: parent
                spacing: 0

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: root.percent + "%"
                    color: Theme.text
                    font.pixelSize: 27
                    font.bold: true
                }

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    visible: appBridge.progressTotal > 0
                    text: appBridge.progressDone + " / " + appBridge.progressTotal + " cues"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontTiny
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 9

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                StatTile {
                    value: Theme.formatClock(root._runElapsed)
                    label: "Elapsed"
                }
                StatTile {
                    value: root._liveEta > 0 ? "~" + Theme.formatClock(root._liveEta) : "—"
                    label: "Remaining"
                    tone: "acc"
                }
                StatTile {
                    value: String(root.windowCount)
                    label: "Stages"
                }
            }

            Rectangle {
                id: bar
                Layout.fillWidth: true
                implicitHeight: 6
                radius: 3
                color: Theme.surfaceRaised
                clip: true

                readonly property bool indeterminate: appBridge.isRunning && appBridge.progressTotal <= 0

                Rectangle {
                    visible: !bar.indeterminate
                    width: bar.width * root.fraction
                    height: bar.height
                    radius: 3
                    color: Theme.accent
                }

                Rectangle {
                    id: indetBar
                    visible: bar.indeterminate
                    width: bar.width / 3
                    height: bar.height
                    radius: 3
                    color: Theme.accent
                    XAnimator on x {
                        running: bar.indeterminate && !Theme.reducedMotion
                        from: 0
                        to: Math.max(0, bar.width - indetBar.width)
                        loops: Animation.Infinite
                        duration: 900
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                visible: appBridge.statusMessage !== ""
                text: appBridge.statusMessage
                color: appBridge.statusState === "failed" ? Theme.error
                       : appBridge.statusState === "cancelled" ? Theme.warning
                       : Theme.textDim
                font.pixelSize: Theme.fontSmall
                elide: Text.ElideRight
            }
        }
    }

    // --- Stage stepper -----------------------------------------------------
    ColumnLayout {
        Layout.fillWidth: true
        visible: appBridge.stageList.length > 0
        spacing: 0

        Label {
            text: "STAGES"
            color: Theme.textMuted
            font.pixelSize: 10
            font.bold: true
            font.letterSpacing: 0.8
        }

        Repeater {
            model: appBridge.stageList

            delegate: Item {
                required property var modelData
                required property int index

                readonly property bool isCurrent: index === appBridge.stageList.length - 1 && appBridge.isRunning

                Layout.fillWidth: true
                Layout.preferredHeight: 40
                Layout.topMargin: index === 0 ? 6 : 0

                // Connector line down to the next step.
                Rectangle {
                    visible: index < appBridge.stageList.length - 1
                    x: 8
                    y: 20
                    width: 1.5
                    height: parent.height - 20
                    color: Theme.border
                }

                Rectangle {
                    x: 0
                    y: 2
                    width: 17
                    height: 17
                    radius: 9
                    color: parent.isCurrent ? Theme.accent : Theme.successTint
                    border.width: parent.isCurrent ? 0 : 1
                    border.color: Theme.border

                    Icon {
                        anchors.centerIn: parent
                        name: parent.parent.isCurrent ? "play" : "check"
                        color: parent.parent.isCurrent ? Theme.accentInk : Theme.success
                        strokeWidth: 2.2
                        width: 10
                        height: 10
                    }
                }

                ColumnLayout {
                    anchors.left: parent.left
                    anchors.leftMargin: 27
                    anchors.right: parent.right
                    spacing: 0

                    Label {
                        Layout.fillWidth: true
                        text: modelData.label
                        color: parent.parent.isCurrent ? Theme.text : Theme.textDim
                        font.pixelSize: Theme.fontBody
                        font.bold: parent.parent.isCurrent
                        elide: Text.ElideRight
                    }

                    Label {
                        Layout.fillWidth: true
                        text: parent.parent.isCurrent
                              ? Theme.formatDuration(root._liveElapsed)
                              : Theme.formatDuration(modelData.elapsed)
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        font.family: Theme.monoFont
                    }
                }
            }
        }
    }
}
