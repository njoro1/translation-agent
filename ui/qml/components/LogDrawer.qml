import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Collapsible bottom log drawer. Collapsed by default; JSON progress lines are
// parsed into the progress panel and hidden unless debug mode is on.
Rectangle {
    id: root

    property bool expanded: appBridge.logVisible

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

                Item { Layout.fillWidth: true }

                Switch {
                    id: debugSwitch
                    checked: appBridge.debugJsonProgress
                    onToggled: appBridge.debugJsonProgress = checked
                    text: "Show raw JSON"
                    font.pixelSize: Theme.fontSmall

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
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: appBridge.logVisible = !appBridge.logVisible
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
                    if (appBridge.logVisible)
                        cursorPosition = text.length
                }
            }
        }
    }
}
