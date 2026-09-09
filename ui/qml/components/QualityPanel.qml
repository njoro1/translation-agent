import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Quality report view: summary badges + issue list.
// UX review S-05: a quality issue row is now clickable and jumps to the
// matching cue in the Review tab; the Type column shows a friendly phrase
// (raw tag kept as a tooltip for power users), and the average CPS badge is
// null-safe (shows "—" instead of a misleading 0.0 when no run exists).
ColumnLayout {
    id: root

    spacing: Theme.md

    function _copySummary() {
        appBridge.copySummaryText()
    }

    // Badges — fluid grid: wraps 7→4→2 cards by window width instead of
    // forcing a 150px×7 single row that overflowed at min window size and
    // stranded half the pane's width on wide screens.
    GridLayout {
        Layout.fillWidth: true
        columns: root.width > 1050 ? 7 : (root.width > 640 ? 4 : 2)
        columnSpacing: Theme.sm
        rowSpacing: Theme.sm

        Repeater {
            model: [
                { label: "Total cues", value: appBridge.qualityTotalCues, tone: Theme.text },
                { label: "Untranslated", value: appBridge.qualityUntranslated,
                  tone: appBridge.qualityUntranslated > 0 ? Theme.error : Theme.success },
                { label: "Errors", value: appBridge.qualityErrors,
                  tone: appBridge.qualityErrors > 0 ? Theme.error : Theme.success },
                { label: "Warnings", value: appBridge.qualityWarnings,
                  tone: appBridge.qualityWarnings > 0 ? Theme.warning : Theme.success },
                { label: "Avg CPS", value: appBridge.qualityAverageCpsText, tone: Theme.text },
                { label: "Max line chars", value: appBridge.qualityMaxLineChars, tone: Theme.text },
                { label: "Strict quality",
                  value: appBridge.resultStrictState === "pass" ? "PASS"
                       : appBridge.resultStrictState === "fail" ? "FAIL" : "OFF",
                  tone: appBridge.resultStrictState === "fail" ? Theme.error
                      : appBridge.resultStrictState === "pass" ? Theme.success : Theme.textMuted }
            ]

            delegate: Rectangle {
                required property var modelData
                Layout.fillWidth: true
                Layout.preferredHeight: 58
                radius: Theme.radiusMd
                color: Theme.surface
                border.color: Theme.border

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 2

                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: modelData.value
                        color: modelData.tone
                        font.pixelSize: Theme.fontTitle
                        font.bold: true
                    }
                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: modelData.label
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                    }
                }
            }
        }
    }

    // Issue header
    Rectangle {
        Layout.fillWidth: true
        implicitHeight: 26
        color: Theme.surfaceAlt
        radius: Theme.radiusSm

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.sm
            anchors.rightMargin: Theme.sm
            spacing: Theme.sm

            Label { text: "Cue"; Layout.preferredWidth: 60; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
            Label { text: "Issue"; Layout.fillWidth: true; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
            Label { text: "Severity"; Layout.preferredWidth: 90; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
        }
    }

    Label {
        Layout.fillWidth: true
        text: "Click an issue to jump to that cue in the Review tab."
        color: Theme.textMuted
        font.pixelSize: Theme.fontSmall
        visible: issueList.count > 0
    }

    ListView {
        id: issueList
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: appBridge.qualityIssuesModel
        spacing: 1
        boundsBehavior: Flickable.StopAtBounds
        keyNavigationEnabled: true
        ScrollBar.vertical: ScrollBar {}

        delegate: Rectangle {
            id: issueRow
            width: issueList.width
            height: 30
            radius: Theme.radiusSm
            color: severity === "error" ? Theme.errorTint
                 : (issueMouse.hovered || ListView.isCurrentItem ? Theme.surfaceAlt : "transparent")

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.sm
                anchors.rightMargin: Theme.sm
                spacing: Theme.sm

                Label {
                    text: cueNumber
                    Layout.preferredWidth: 60
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                }
                Label {
                    text: friendlyType
                    Layout.fillWidth: true
                    color: Theme.text
                    font.pixelSize: Theme.fontSmall
                    elide: Text.ElideRight
                }
                Label {
                    text: severity.toUpperCase()
                    Layout.preferredWidth: 90
                    color: severity === "error" ? Theme.error : Theme.warning
                    font.pixelSize: Theme.fontSmall
                    font.bold: true
                }
            }

            // Raw tag (e.g. cjk_residue_error) kept as a tooltip for power users.
            ToolTip.text: "Cue " + cueNumber + " · " + rawType + "\n" + message
            ToolTip.visible: issueMouse.hovered
            ToolTip.delay: 300

            HoverHandler { id: issueMouse }

            TapHandler {
                onTapped: appBridge.revealCue(cueNumber)
            }

            Keys.onReturnPressed: appBridge.revealCue(cueNumber)
            Keys.onEnterPressed: appBridge.revealCue(cueNumber)

            Accessible.role: Accessible.ListItem
            Accessible.name: "Quality issue on cue " + cueNumber + ": " + friendlyType
                            + " (" + severity + "). Activate to open the cue in the Review tab."
            Accessible.description: message
        }

        Text {
            anchors.centerIn: parent
            visible: issueList.count === 0
            text: appBridge.resultReady ? "No issues reported." : "Run a translation to see its quality report here."
            color: Theme.textMuted
            font.pixelSize: Theme.fontLabel
        }
    }

    RowLayout {
        spacing: Theme.sm

        Button {
            text: "Copy report summary"
            Accessible.name: "Copy quality report summary to clipboard"
            onClicked: root._copySummary()

            background: Rectangle {
                radius: Theme.radiusSm
                color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                border.color: Theme.border
            }
            contentItem: Label {
                text: parent.text
                color: Theme.text
                font.pixelSize: Theme.fontSmall
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }

        Item { Layout.fillWidth: true }
    }
}
