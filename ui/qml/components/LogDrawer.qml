import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Collapsible bottom log drawer. Collapsed by default; JSON progress lines are
// parsed into the progress panel and hidden unless debug mode is on.
Rectangle {
    id: root

    property bool expanded: appBridge.logVisible
    // Error/warning counts for the at-a-glance header badge.
    // Counted incrementally in Python as lines arrive. This used to re-run a
    // global regex over the entire log on every append (O(n^2) for a long run)
    // and only matched a literal "[error]" prefix, so tracebacks and yt-dlp
    // "ERROR:" lines were missed and the badge under-reported.
    readonly property int errorCount: appBridge.logErrorCount
    readonly property int warnCount: appBridge.logWarnCount

    color: Theme.surface
    border.color: Theme.border
    border.width: 1
    implicitHeight: expanded ? 200 : 34

    Behavior on implicitHeight { NumberAnimation { duration: 140 } }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Handle row (always visible)
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 33
            color: Theme.surfaceAlt

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.md
                anchors.rightMargin: Theme.sm
                spacing: Theme.sm

                Label {
                    text: root.expanded ? "\u25BC" : "\u25B2"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                }

                Label {
                    text: "Log"
                    color: Theme.text
                    font.pixelSize: Theme.fontSmall
                    font.bold: true
                }

                // At-a-glance health badge: visible only when something
                // needs attention, so an all-green run stays uncluttered.
                Rectangle {
                    visible: root.errorCount > 0 || root.warnCount > 0
                    implicitWidth: errLabel.implicitWidth + 12
                    implicitHeight: 18
                    radius: 9
                    color: root.errorCount > 0 ? Theme.errorTint : Theme.warningTint

                    Label {
                        id: errLabel
                        anchors.centerIn: parent
                        text: root.errorCount > 0
                              ? root.errorCount + " error" + (root.errorCount === 1 ? "" : "s")
                              : root.warnCount + " warning" + (root.warnCount === 1 ? "" : "s")
                        color: root.errorCount > 0 ? Theme.error : Theme.warning
                        font.pixelSize: 10
                        font.bold: true
                    }
                }

                // Jump straight to the cause instead of scrolling a long run.
                Button {
                    flat: true
                    visible: root.errorCount > 0
                    text: "First error"
                    onClicked: {
                        appBridge.logVisible = true
                        const pos = appBridge.logFirstErrorPosition()
                        if (pos >= 0) {
                            logArea.cursorPosition = pos
                            logArea.select(pos, pos + 1)
                        }
                    }

                    background: Rectangle {
                        color: parent.hovered ? Theme.border : "transparent"
                        radius: Theme.radiusSm
                    }
                    contentItem: Label {
                        text: parent.text
                        color: Theme.error
                        font.pixelSize: Theme.fontSmall
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    Accessible.name: "Jump to first error in log"
                    Accessible.role: Accessible.Button
                }

                Item { Layout.fillWidth: true }

                Switch {
                    id: debugSwitch
                    checked: appBridge.debugJsonProgress
                    onToggled: appBridge.debugJsonProgress = checked
                    text: "Show raw JSON"
                    font.pixelSize: Theme.fontSmall

                    Accessible.name: "Show raw JSON progress lines"
                    // QML's Accessible does not expose CheckableMenuItem (it
                    // resolved to undefined and logged a warning on load); a
                    // Switch is announced as a CheckBox.
                    Accessible.role: Accessible.CheckBox

                    indicator: Rectangle {
                        implicitWidth: 30
                        implicitHeight: 16
                        radius: 8
                        color: debugSwitch.checked ? Theme.accent : Theme.border

                        Rectangle {
                            x: debugSwitch.checked ? parent.width - width - 2 : 2
                            anchors.verticalCenter: parent.verticalCenter
                            width: 12
                            height: 12
                            radius: 6
                            color: "#FFFFFF"

                            Behavior on x { NumberAnimation { duration: 120 } }
                        }
                    }

                    contentItem: Label {
                        text: debugSwitch.text
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        verticalAlignment: Text.AlignVCenter
                        leftPadding: debugSwitch.indicator.width + 6
                    }
                }

                Button {
                    flat: true
                    text: "Copy"
                    onClicked: appBridge.copyLog()

                    background: Rectangle {
                        color: parent.hovered ? Theme.border : "transparent"
                        radius: Theme.radiusSm
                    }
                    contentItem: Label {
                        text: parent.text
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    Accessible.name: "Copy log to clipboard"
                    Accessible.role: Accessible.Button
                }

                Button {
                    flat: true
                    text: "Clear"
                    onClicked: appBridge.clearLog()

                    background: Rectangle {
                        color: parent.hovered ? Theme.border : "transparent"
                        radius: Theme.radiusSm
                    }
                    contentItem: Label {
                        text: parent.text
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }

                    Accessible.name: "Clear log"
                    Accessible.role: Accessible.Button
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: appBridge.logVisible = !appBridge.logVisible
                // Below the row (z: -1): clicks on empty handle space toggle
                // the drawer, while the Switch/Copy/Clear controls on top of
                // the row keep receiving their own clicks.
                z: -1
            }
        }

        ScrollView {
            id: scroller
            visible: root.expanded
            Layout.fillWidth: true
            Layout.fillHeight: true

            TextArea {
                id: logArea
                readOnly: true
                wrapMode: TextArea.NoWrap
                textFormat: TextEdit.PlainText
                font.family: "Consolas"
                font.pixelSize: Theme.fontSmall
                color: Theme.text
                text: appBridge.logText
                persistentSelection: true

                background: Rectangle { color: "transparent" }

                onTextChanged: {
                    // Follow the tail while expanded, including live during a
                    // run (previously only scrolled when the drawer was
                    // already open AND stole focus; now purely text-driven).
                    if (appBridge.logVisible)
                        cursorPosition = text.length
                }
            }
        }
    }
}
