import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

// Quality screen: score ring + the seven headline numbers, then the issue list
// and the distributions, then the gate / thresholds / run context / export
// panel. Every number here comes from the run's result JSON — nothing is
// recomputed in QML.
Item {
    id: root

    readonly property var issues: appBridge.qualityIssuesModel

    signal navigateRequested(int page)

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight + 36
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            id: content
            x: 18
            y: 18
            width: flick.width - 36
            spacing: 16

            // ==================================================== SCORE ROW ==
            AppCard {
                Layout.fillWidth: true

                RowLayout {
                    width: parent.width
                    spacing: 24

                    // --- Ring + grade ---------------------------------------
                    RowLayout {
                        Layout.preferredWidth: 232
                        spacing: 14

                        Item {
                            implicitWidth: 96
                            implicitHeight: 96

                            ProgressRing {
                                anchors.fill: parent
                                value: appBridge.qualityScore / 100.0
                                thickness: 8
                                valueColor: Theme.toneColor(appBridge.qualityScoreTone)
                            }

                            ColumnLayout {
                                anchors.centerIn: parent
                                spacing: 0

                                Label {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: appBridge.resultReady ? String(appBridge.qualityScore) : "\u2014"
                                    color: Theme.text
                                    font.pixelSize: 24
                                    font.bold: true
                                    font.letterSpacing: -0.8
                                }

                                Label {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: "/ 100"
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.fontTiny
                                }
                            }
                        }

                        ColumnLayout {
                            spacing: 2

                            Label {
                                text: appBridge.resultReady ? appBridge.qualityGrade : "No report"
                                color: Theme.text
                                font.pixelSize: Theme.fontH2
                                font.bold: true
                            }

                            Label {
                                text: appBridge.resultReady
                                      ? appBridge.qualityTotalCues + " cues scored"
                                      : "Run a translation first"
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSmall
                            }
                        }

                        Item { Layout.fillWidth: true }
                    }

                    // --- Seven headline numbers -----------------------------
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        Repeater {
                            model: appBridge.qualityTiles

                            delegate: StatTile {
                                required property var modelData
                                value: modelData.value
                                label: modelData.label
                                tone: modelData.tone
                                hint: modelData.hint
                            }
                        }
                    }
                }
            }

            // =============================================== ISSUES + SIDE ==
            RowLayout {
                Layout.fillWidth: true
                spacing: 16

                // ------------------------------------------------- LEFT -----
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 420
                    spacing: 16

                    AppCard {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 420
                        title: "Issues"
                        headerExtra: [
                            Chip {
                                text: String(issueList.count)
                                mono: true
                            }
                        ]

                        ColumnLayout {
                            width: parent.width
                            height: parent.height
                            spacing: 8

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                FilterChip {
                                    text: "All"
                                    checked: root.issues.filterMode === "all"
                                    onClicked: root.issues.filterMode = "all"
                                }
                                FilterChip {
                                    text: "Errors"
                                    iconName: "x"
                                    checked: root.issues.filterMode === "errors"
                                    onClicked: root.issues.filterMode = "errors"
                                }
                                FilterChip {
                                    text: "Warnings"
                                    iconName: "alert"
                                    checked: root.issues.filterMode === "warnings"
                                    onClicked: root.issues.filterMode = "warnings"
                                }

                                Item { Layout.fillWidth: true }

                                AppButton {
                                    text: "Re-check"
                                    small: true
                                    variant: "ghost"
                                    iconName: "refresh"
                                    enabled: appBridge.resultReady
                                    onClicked: appBridge.recheckQuality()
                                }
                            }

                            // --- Header -------------------------------------
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: 28
                                radius: Theme.radiusSm
                                color: Theme.surfaceAlt

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 10
                                    anchors.rightMargin: 10
                                    spacing: 8

                                    Label { text: "CUE"; Layout.preferredWidth: 46; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                    Label { text: "TYPE"; Layout.preferredWidth: 190; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                    Label { text: "SEVERITY"; Layout.preferredWidth: 104; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                    Label { text: "MESSAGE"; Layout.fillWidth: true; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                    Label { text: ""; Layout.preferredWidth: 100; color: Theme.textMuted; font.pixelSize: 10 }
                                }
                            }

                            // --- Rows ---------------------------------------
                            ListView {
                                id: issueList
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                model: root.issues
                                spacing: 1
                                boundsBehavior: Flickable.StopAtBounds
                                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                                delegate: Rectangle {
                                    id: issueRow
                                    required property int cueNumber
                                    required property string issueType
                                    required property string severity
                                    required property string message

                                    readonly property bool isError: issueRow.severity === "error"

                                    width: issueList.width
                                    height: 32
                                    radius: Theme.radiusXs
                                    color: issueRow.isError ? Theme.errorTint
                                                            : (issueHover.hovered ? Theme.surfaceAlt : Theme.warningTint)

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10
                                        spacing: 8

                                        Label {
                                            text: String(issueRow.cueNumber)
                                            Layout.preferredWidth: 46
                                            color: Theme.textDim
                                            font.pixelSize: Theme.fontTiny
                                            font.family: Theme.monoFont
                                        }

                                        Label {
                                            text: issueRow.issueType
                                            Layout.preferredWidth: 190
                                            color: Theme.textDim
                                            font.pixelSize: Theme.fontTiny
                                            font.family: Theme.monoFont
                                            elide: Text.ElideRight
                                        }

                                        Chip {
                                            Layout.preferredWidth: 104
                                            text: issueRow.isError ? "ERROR" : "WARNING"
                                            tone: issueRow.isError ? "err" : "warn"
                                            iconName: issueRow.isError ? "x" : "alert"
                                        }

                                        Label {
                                            Layout.fillWidth: true
                                            text: issueRow.message
                                            color: Theme.textDim
                                            font.pixelSize: Theme.fontBody
                                            elide: Text.ElideRight
                                        }

                                        AppButton {
                                            Layout.preferredWidth: 100
                                            text: "Fix in Review"
                                            small: true
                                            onClicked: appBridge.revealCue(issueRow.cueNumber)
                                        }
                                    }

                                    HoverHandler { id: issueHover }
                                }

                                Text {
                                    anchors.centerIn: parent
                                    width: parent.width - 40
                                    horizontalAlignment: Text.AlignHCenter
                                    wrapMode: Text.WordWrap
                                    visible: issueList.count === 0
                                    text: appBridge.resultReady
                                          ? "No issues match this filter."
                                          : "Run a translation to see its quality issues."
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.fontBody
                                }
                            }
                        }
                    }

                    AppCard {
                        Layout.fillWidth: true
                        title: "Distributions"

                        RowLayout {
                            width: parent.width
                            spacing: 24

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8

                                    Label {
                                        text: "Reading speed (CPS)"
                                        color: Theme.text
                                        font.pixelSize: Theme.fontBody
                                        font.bold: true
                                    }
                                    Item { Layout.fillWidth: true }
                                    Label {
                                        text: appBridge.qualityCpsHistogram.summary
                                        color: Theme.textMuted
                                        font.pixelSize: Theme.fontTiny
                                    }
                                }

                                Histogram {
                                    Layout.fillWidth: true
                                    bars: appBridge.qualityCpsHistogram.bars
                                    labels: appBridge.qualityCpsHistogram.labels
                                }

                                RowLayout {
                                    spacing: 14

                                    RowLayout {
                                        spacing: 5
                                        Rectangle { implicitWidth: 9; implicitHeight: 9; radius: 2; color: Theme.accent }
                                        Label { text: "in range"; color: Theme.textMuted; font.pixelSize: Theme.fontTiny }
                                    }
                                    RowLayout {
                                        spacing: 5
                                        Rectangle { implicitWidth: 9; implicitHeight: 9; radius: 2; color: Theme.warning }
                                        Label { text: "over the warning threshold"; color: Theme.textMuted; font.pixelSize: Theme.fontTiny }
                                    }
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 6

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8

                                    Label {
                                        text: "Cue duration"
                                        color: Theme.text
                                        font.pixelSize: Theme.fontBody
                                        font.bold: true
                                    }
                                    Item { Layout.fillWidth: true }
                                    Label {
                                        text: appBridge.qualityDurationHistogram.summary
                                        color: Theme.textMuted
                                        font.pixelSize: Theme.fontTiny
                                    }
                                }

                                Histogram {
                                    Layout.fillWidth: true
                                    bars: appBridge.qualityDurationHistogram.bars
                                    labels: appBridge.qualityDurationHistogram.labels
                                }

                                RowLayout {
                                    spacing: 14

                                    RowLayout {
                                        spacing: 5
                                        Rectangle { implicitWidth: 9; implicitHeight: 9; radius: 2; color: Theme.accent }
                                        Label { text: "in range"; color: Theme.textMuted; font.pixelSize: Theme.fontTiny }
                                    }
                                    RowLayout {
                                        spacing: 5
                                        Rectangle { implicitWidth: 9; implicitHeight: 9; radius: 2; color: Theme.warning }
                                        Label { text: "outside the target duration"; color: Theme.textMuted; font.pixelSize: Theme.fontTiny }
                                    }
                                }
                            }
                        }
                    }
                }

                // ------------------------------------------------ RIGHT -----
                ColumnLayout {
                    Layout.preferredWidth: 400
                    Layout.minimumWidth: 320
                    spacing: 16

                    AppCard {
                        Layout.fillWidth: true
                        title: "Gate"
                        headerExtra: [
                            AppSwitch {
                                text: "Strict"
                                checked: appBridge.strictQuality
                                onToggled: appBridge.strictQuality = checked
                                accessibleName: "Strict quality gate"
                            }
                        ]

                        ColumnLayout {
                            width: parent.width
                            spacing: 10

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Pill {
                                    tone: appBridge.resultStrictState === "fail" ? "err"
                                          : appBridge.resultStrictState === "pass" ? "ok" : "mute"
                                    text: appBridge.resultStrictState === "fail" ? "Exit 1"
                                          : appBridge.resultStrictState === "pass" ? "Exit 0" : "Off"
                                }

                                Label {
                                    Layout.fillWidth: true
                                    text: {
                                        if (!appBridge.resultReady)
                                            return "No run loaded yet."
                                        if (appBridge.resultStrictState === "fail")
                                            return appBridge.qualityErrors + " error(s) block the run"
                                        if (appBridge.resultStrictState === "pass")
                                            return "The gate would let this run through."
                                        return "The gate is off for this run."
                                    }
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.fontSmall
                                    wrapMode: Text.WordWrap
                                }
                            }

                            AppButton {
                                Layout.fillWidth: true
                                text: "Re-run with the gate off"
                                small: true
                                iconName: "refresh"
                                enabled: appBridge.resultReady && !appBridge.isRunning
                                onClicked: {
                                    appBridge.strictQuality = false
                                    appBridge.rerunLastRun()
                                }
                                Accessible.name: "Turn the strict gate off and re-run the last settings"
                            }
                        }
                    }

                    AppCard {
                        Layout.fillWidth: true
                        title: "Thresholds"
                        note: "from the active preset"

                        ColumnLayout {
                            width: parent.width
                            spacing: 7

                            Repeater {
                                model: appBridge.qualityThresholds

                                delegate: KeyValue {
                                    required property var modelData
                                    key: modelData.k
                                    value: modelData.v
                                    valueColor: modelData.tone === "err" ? Theme.error
                                              : modelData.tone === "warn" ? Theme.warning
                                              : Theme.text
                                    mono: modelData.mono === true
                                }
                            }
                        }
                    }

                    AppCard {
                        Layout.fillWidth: true
                        title: "Run context"

                        ColumnLayout {
                            width: parent.width
                            spacing: 7

                            Repeater {
                                model: appBridge.runContext

                                delegate: KeyValue {
                                    required property var modelData
                                    key: modelData.k
                                    value: modelData.v
                                    mono: modelData.mono === true
                                }
                            }
                        }
                    }

                    AppCard {
                        Layout.fillWidth: true
                        title: "Export"

                        ColumnLayout {
                            width: parent.width
                            spacing: 8

                            AppButton {
                                Layout.fillWidth: true
                                text: "quality_report.json"
                                small: true
                                iconName: "file"
                                enabled: appBridge.resultReady
                                onClicked: appBridge.exportQualityReport()
                            }

                            AppButton {
                                Layout.fillWidth: true
                                text: "Issue list as CSV"
                                small: true
                                iconName: "list"
                                enabled: appBridge.resultReady
                                onClicked: appBridge.exportIssueCsv()
                            }
                        }
                    }
                }
            }
        }
    }
}
