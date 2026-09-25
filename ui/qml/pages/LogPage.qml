import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

// Log screen: run history on the left, the full console on the right. The
// history is persisted, so a previous session's runs are still selectable.
Item {
    id: root

    property string filterQuery: ""

    signal navigateRequested(int page)

    RowLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16

        // =========================================================== LEFT ==
        ColumnLayout {
            Layout.preferredWidth: 288
            Layout.minimumWidth: 240
            // A nested layout containing `fillWidth` children reports a greedy
            // size policy to its parent RowLayout, which then hands it every
            // spare pixel and collapses the sibling column to ~0. The maximum
            // pins the column to its preferred width.
            Layout.maximumWidth: 288
            Layout.fillHeight: true
            spacing: 16

            AppCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: "Run history"
                headerExtra: [
                    AppButton {
                        text: "Clear"
                        small: true
                        variant: "ghost"
                        iconName: "x"
                        enabled: appBridge.runHistory.length > 0
                        onClicked: appBridge.clearRunHistory()
                        Accessible.name: "Clear the run history"
                    }
                ]

                ListView {
                    id: historyList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: appBridge.runHistory
                    spacing: 3
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    delegate: Rectangle {
                        id: runItem
                        required property var modelData
                        required property int index

                        readonly property bool isOn: appBridge.selectedRunIndex === index

                        width: historyList.width
                        height: runBody.implicitHeight + 20
                        radius: Theme.radiusSm
                        color: runItem.isOn ? Theme.accentSoft
                                            : (runHover.hovered ? Theme.surfaceAlt : "transparent")
                        border.width: runItem.isOn ? 1 : 0
                        border.color: Theme.accentLine

                        ColumnLayout {
                            id: runBody
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 11
                            anchors.rightMargin: 11
                            spacing: 4

                            // Title + outcome. The compact `YT`/`LC`/`OFF` code
                            // that used to sit here was a legend the user had to
                            // be taught; the source and engine are spelled out on
                            // the line below instead (§2.2).
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Label {
                                    Layout.fillWidth: true
                                    text: runItem.modelData.title
                                    color: Theme.text
                                    font.pixelSize: Theme.fontSmall
                                    font.bold: true
                                    elide: Text.ElideMiddle
                                }

                                Chip {
                                    text: runItem.modelData.resultText
                                    tone: runItem.modelData.resultTone
                                    iconName: runItem.modelData.resultTone === "ok" ? "check"
                                            : runItem.modelData.resultTone === "warn" ? "alert" : "x"
                                    mono: true
                                }
                            }

                            // Timestamp (the review's §9 "each entry = timestamp,
                            // source, engine, outcome").
                            Label {
                                text: runItem.modelData.started + " \u00b7 "
                                      + runItem.modelData.duration
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontTiny
                                font.family: Theme.monoFont
                            }

                            Label {
                                id: runMeta
                                Layout.fillWidth: true
                                text: (runItem.modelData.sourceLabel || "\u2014")
                                      + " \u00b7 " + (runItem.modelData.engineLabel || "\u2014")
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontTiny
                                elide: Text.ElideRight
                                ToolTip.visible: runHover.hovered
                                ToolTip.delay: 700
                                ToolTip.text: runMeta.text
                            }
                        }

                        HoverHandler { id: runHover }

                        // Selecting a row also *opens* it: Review and Quality
                        // follow the selection, or the history is a list of rows
                        // that can be highlighted but never read (§9).
                        TapHandler {
                            onTapped: appBridge.selectRun(runItem.index)
                        }

                        Accessible.role: Accessible.ListItem
                        Accessible.name: runItem.modelData.title
                        Accessible.selected: runItem.isOn
                    }

                    Text {
                        anchors.centerIn: parent
                        width: parent.width - 24
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        visible: historyList.count === 0
                        text: "No runs recorded yet."
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                    }
                }
            }

            AppCard {
                Layout.fillWidth: true
                visible: appBridge.selectedRunIndex >= 0
                title: "Selected run"

                ColumnLayout {
                    width: parent.width
                    spacing: 7

                    Repeater {
                        model: appBridge.selectedRunRows

                        delegate: KeyValue {
                            required property var modelData
                            key: modelData.k
                            value: modelData.v
                            valueColor: modelData.tone === "ok" ? Theme.success
                                      : modelData.tone === "err" ? Theme.error
                                      : Theme.text
                            mono: modelData.mono === true
                        }
                    }

                    // Opening a run can fail (a failed run wrote no result, or
                    // its archive was pruned). Saying so beats a row that
                    // silently refuses to load.
                    RowLayout {
                        Layout.fillWidth: true
                        visible: !appBridge.selectedRunOpenable
                        spacing: 7

                        StatusMark {
                            status: "todo"
                            Layout.alignment: Qt.AlignTop
                        }

                        Label {
                            Layout.fillWidth: true
                            text: appBridge.selectedRunProblem
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontTiny
                            wrapMode: Text.WordWrap
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 1
                        color: Theme.borderSoft
                    }

                    AppButton {
                        Layout.fillWidth: true
                        text: "Re-run the most recent run"
                        small: true
                        iconName: "refresh"
                        // The settings snapshot is only kept for the newest run,
                        // so this is offered only while that is the one selected.
                        enabled: !appBridge.isRunning && appBridge.selectedRunIndex === 0
                        onClicked: appBridge.rerunLastRun()
                    }
                }
            }

            Item { Layout.fillHeight: true }
        }

        // ========================================================== RIGHT ==
        AppCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: "Console"

            headerExtra: [
                // No "empty" chip here. It sat among the level filters and read
                // as one, so the review filed it as an unexplained filter
                // (§9 #36). It carried no filtering behaviour and duplicated
                // both the console's empty prompt and the "0 of 0 lines"
                // counter, so it was removed rather than relabelled.
                FilterChip {
                    text: "All"
                    count: String(consoleView.counts.all)
                    checked: consoleView.toneFilter === ""
                    onClicked: consoleView.toneFilter = ""
                },
                FilterChip {
                    text: "Info"
                    count: String(consoleView.counts.info)
                    checked: consoleView.toneFilter === "info"
                    onClicked: consoleView.toneFilter = "info"
                },
                FilterChip {
                    text: "Warn"
                    count: String(consoleView.counts.warn)
                    checked: consoleView.toneFilter === "warn"
                    onClicked: consoleView.toneFilter = "warn"
                },
                FilterChip {
                    text: "Error"
                    count: String(consoleView.counts.err)
                    checked: consoleView.toneFilter === "err"
                    onClicked: consoleView.toneFilter = "err"
                },
                AppSwitch {
                    text: "Follow"
                    checked: appBridge.logVisible
                    onToggled: appBridge.logVisible = checked
                    accessibleName: "Follow the log tail"
                }
            ]

            ColumnLayout {
                width: parent.width
                height: parent.height
                spacing: 8

                ConsoleView {
                    id: consoleView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    query: root.filterQuery
                    follow: appBridge.logVisible
                    emptyText: "Nothing logged yet. Press Run on the Run screen."
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Label {
                        text: consoleView.lineCount + " of " + consoleView.counts.all + " lines"
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontTiny
                        font.family: Theme.monoFont
                    }

                    Item { Layout.fillWidth: true }

                    AppButton {
                        text: "Copy"
                        small: true
                        variant: "ghost"
                        iconName: "copy"
                        enabled: appBridge.logText !== ""
                        onClicked: appBridge.copyLog()
                    }

                    AppButton {
                        text: "Export"
                        small: true
                        variant: "ghost"
                        iconName: "download"
                        enabled: appBridge.logText !== ""
                        onClicked: appBridge.exportLog()
                    }

                    AppButton {
                        text: "Clear"
                        small: true
                        variant: "ghost"
                        iconName: "x"
                        enabled: appBridge.logText !== ""
                        onClicked: appBridge.clearLog()
                    }
                }
            }
        }
    }
}
