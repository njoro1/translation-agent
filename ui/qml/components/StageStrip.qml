import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// The Run screen's stage strip (UI review 6.2, 6.6).
//
// Source -> Transcribe -> Translate -> Gate -> Write.
//
// The middle column used to be called `PIPELINE` while being a form, so the
// name over-promised a flow that did not exist. This strip honours the name:
// idle-grey normally, lighting per stage during a run, and halting on the
// failing stage when a run fails — which finally gives the run-in-progress and
// failed states a home instead of inventing a second vocabulary mid-run.
//
// Stage states come from `AppBridge.pipelineStages`:
//   pending  grey, hollow dot
//   active   accent, filled dot, pulse unless Reduce motion
//   done     success, check
//   failed   error, cross
//   skipped  muted, dash — a fact about the mode, not a problem
RowLayout {
    id: root

    objectName: "run.stageStrip"

    spacing: 0

    readonly property var stages: appBridge.pipelineStages
    readonly property int activeIndex: appBridge.pipelineStageIndex

    Repeater {
        model: root.stages

        delegate: RowLayout {
            id: stageRow
            required property var modelData
            required property int index

            spacing: 0

            readonly property string state: modelData.state
            readonly property bool isActive: state === "active"
            readonly property bool isDone: state === "done"
            readonly property bool isFailed: state === "failed"
            readonly property bool isSkipped: state === "skipped"
            readonly property bool reached: isActive || isDone || isFailed

            // Connector from the previous stage.
            Rectangle {
                visible: stageRow.index > 0
                implicitWidth: 18
                implicitHeight: 2
                color: stageRow.reached || (stageRow.index - 1) < root.activeIndex
                       ? Theme.accentLine : Theme.border
            }

            RowLayout {
                spacing: 6

                Rectangle {
                    implicitWidth: 16
                    implicitHeight: 16
                    radius: 8
                    color: stageRow.isActive ? Theme.accent
                         : stageRow.isDone ? Theme.successTint
                         : stageRow.isFailed ? Theme.error
                         : "transparent"
                    border.width: stageRow.reached ? 0 : 1.5
                    border.color: Theme.borderStrong

                    Icon {
                        anchors.centerIn: parent
                        visible: stageRow.isDone || stageRow.isFailed
                        name: stageRow.isFailed ? "x" : "check"
                        color: stageRow.isFailed ? "#FFFFFF" : Theme.success
                        strokeWidth: 2.6
                        width: 10
                        height: 10
                    }

                    Label {
                        anchors.centerIn: parent
                        visible: stageRow.isSkipped
                        text: "\u2013"
                        color: Theme.textMuted
                        font.pixelSize: 11
                        font.bold: true
                    }

                    // The active stage pulses, unless Reduce motion is on.
                    SequentialAnimation on opacity {
                        running: stageRow.isActive && !Theme.reducedMotion
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.45; duration: 700 }
                        NumberAnimation { to: 1.0; duration: 700 }
                    }
                }

                Label {
                    text: stageRow.modelData.label
                    color: stageRow.isActive ? Theme.text
                         : stageRow.isFailed ? Theme.error
                         : stageRow.isSkipped ? Theme.textMuted
                         : stageRow.isDone ? Theme.textDim
                         : Theme.textMuted
                    font.pixelSize: Theme.fontTiny
                    font.bold: stageRow.isActive || stageRow.isFailed
                }
            }
        }
    }

    Item { Layout.fillWidth: true }

    Accessible.role: Accessible.StaticText
    Accessible.name: {
        var parts = []
        for (var i = 0; i < root.stages.length; i++) {
            var s = root.stages[i]
            if (s.state === "skipped") continue
            parts.push(s.label + " " + s.state)
        }
        return "Pipeline stages: " + parts.join(", ")
    }
}
