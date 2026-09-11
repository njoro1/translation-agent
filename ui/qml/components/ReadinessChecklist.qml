import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Pre-run readiness checklist, rendered from ``appBridge.readinessRows``.
//
// The state machine lives in Python (testable, with a real ``n/a`` state) — this
// component is only a renderer. A row that can never fail teaches users to
// ignore the checklist, so nothing here is hardcoded green.
ColumnLayout {
    id: root

    spacing: 2

    readonly property var rows: appBridge.readinessRows

    function readyCount() {
        var n = 0
        for (var i = 0; i < rows.length; i++)
            if (rows[i].state === "ok") n++
        return n
    }

    function requiredCount() {
        var n = 0
        for (var i = 0; i < rows.length; i++)
            if (rows[i].state !== "n/a") n++
        return n
    }

    Repeater {
        model: root.rows

        delegate: Rectangle {
            id: row
            required property var modelData

            readonly property bool isOk: modelData.state === "ok"
            readonly property bool isNa: modelData.state === "n/a"

            Layout.fillWidth: true
            implicitHeight: rowLayout.implicitHeight + 16
            radius: Theme.radiusSm
            color: rowHover.hovered ? Theme.surfaceAlt : "transparent"

            RowLayout {
                id: rowLayout
                anchors.fill: parent
                anchors.leftMargin: 9
                anchors.rightMargin: 9
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 18
                    Layout.preferredHeight: 18
                    Layout.alignment: Qt.AlignTop
                    radius: 9
                    color: row.isOk ? Theme.successTint : row.isNa ? Theme.surfaceRaised : Theme.warningTint

                    Icon {
                        anchors.centerIn: parent
                        name: row.isOk ? "check" : row.isNa ? "minus" : "alert"
                        color: row.isOk ? Theme.success : row.isNa ? Theme.textMuted : Theme.warning
                        strokeWidth: 2.4
                        width: 11
                        height: 11
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1

                    Label {
                        Layout.fillWidth: true
                        text: modelData.label
                        color: row.isOk ? Theme.text : Theme.textDim
                        font.pixelSize: Theme.fontBody
                        font.bold: row.isOk
                        elide: Text.ElideRight
                    }

                    Label {
                        Layout.fillWidth: true
                        visible: modelData.hint !== ""
                        text: modelData.hint
                        color: row.isNa ? Theme.textMuted : Theme.warning
                        font.pixelSize: Theme.fontSmall
                        wrapMode: Text.WordWrap
                    }
                }

                Label {
                    visible: row.isNa
                    text: "n/a"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                }
            }

            HoverHandler { id: rowHover }

            Accessible.role: Accessible.StaticText
            Accessible.name: modelData.label + ": "
                             + (row.isOk ? "ready"
                                : row.isNa ? "not needed" : modelData.hint)
        }
    }
}
