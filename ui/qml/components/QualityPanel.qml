import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Quality report view: summary badges + issue list.
ColumnLayout {
    id: root

    spacing: Theme.md

    function _copySummary() {
        appBridge.copySummaryText()
    }

    // Badges
    GridLayout {
        Layout.fillWidth: true
        columns: 7
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
                { label: "Avg CPS", value: appBridge.qualityAverageCps.toFixed(1), tone: Theme.text },
                { label: "Max line chars", value: appBridge.qualityMaxLineChars, tone: Theme.text },
                { label: "Strict quality",
                  value: appBridge.resultStrictState === "pass" ? "PASS"
                       : appBridge.resultStrictState === "fail" ? "FAIL" : "OFF",
                  tone: appBridge.resultStrictState === "fail" ? Theme.error
                      : appBridge.resultStrictState === "pass" ? Theme.success : Theme.textMuted }
            ]

            delegate: Rectangle {
                required property var modelData
                Layout.preferredWidth: 150
                implicitHeight: 58
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
            Label { text: "Type"; Layout.preferredWidth: 240; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
            Label { text: "Severity"; Layout.preferredWidth: 80; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
            Label { text: "Message"; Layout.fillWidth: true; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; font.bold: true }
        }
    }

    ListView {
        id: issueList
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: appBridge.qualityIssuesModel
        spacing: 1
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar {}

        delegate: Rectangle {
            width: issueList.width
            height: 28
            radius: Theme.radiusSm
            color: severity === "error" ? Theme.errorTint : (issueMouse.hovered ? Theme.surfaceAlt : "transparent")

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.sm
                anchors.rightMargin: Theme.sm
                spacing: Theme.sm

                Label { text: cueNumber; Layout.preferredWidth: 60; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                Label { text: issueType; Layout.preferredWidth: 240; color: Theme.text; font.pixelSize: Theme.fontSmall; elide: Text.ElideRight }
                Label {
                    text: severity.toUpperCase()
                    Layout.preferredWidth: 80
                    color: severity === "error" ? Theme.error : Theme.warning
                    font.pixelSize: Theme.fontSmall
                    font.bold: true
                }
                Label { text: message; Layout.fillWidth: true; color: Theme.textMuted; font.pixelSize: Theme.fontSmall; elide: Text.ElideRight }
            }

            HoverHandler { id: issueMouse }
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
