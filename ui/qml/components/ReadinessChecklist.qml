import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Pre-run readiness checklist.
//
// Rewritten as a thin renderer over `appBridge.readinessRows`. Two rows used to
// be hardcoded green in QML (`_outputReady()` returned true unconditionally, and
// the ASR row showed a tick plus an irrelevant hint in YouTube mode). A row that
// can never fail teaches users to ignore the checklist, so the state machine now
// lives in Python where it is testable, and includes a real `n/a` state.
ColumnLayout {
    id: root

    spacing: Theme.xs

    Repeater {
        model: appBridge.readinessRows

        delegate: RowLayout {
            id: row
            required property var modelData

            readonly property bool isOk: modelData.state === "ok"
            readonly property bool isNa: modelData.state === "n/a"

            spacing: Theme.sm
            Layout.fillWidth: true

            Label {
                text: row.isOk ? "\u2713" : row.isNa ? "\u2013" : "\u00D7"
                color: row.isOk ? Theme.success : row.isNa ? Theme.textMuted : Theme.warning
                font.pixelSize: Theme.fontBody
                font.bold: true
                opacity: row.isNa ? 0.6 : 1

                Accessible.ignored: true
            }

            Label {
                text: modelData.label
                color: row.isOk ? Theme.text : Theme.textMuted
                font.pixelSize: Theme.fontBody
                opacity: row.isNa ? 0.6 : 1
            }

            Label {
                visible: modelData.hint !== ""
                text: "\u2014 " + modelData.hint
                color: Theme.textMuted
                font.pixelSize: Theme.fontSmall
                elide: Text.ElideRight
                Layout.fillWidth: true
                Layout.maximumWidth: 260
            }

            Item { Layout.fillWidth: true }

            Accessible.role: Accessible.StaticText
            Accessible.name: modelData.label + ": "
                             + (row.isOk ? "ready"
                                : row.isNa ? "not needed" : modelData.hint)
        }
    }
}
