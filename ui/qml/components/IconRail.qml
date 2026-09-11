import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Left icon rail: the app's five destinations plus the palette shortcut.
Rectangle {
    id: root

    property int currentIndex: 0
    property int reviewBadge: 0
    property bool showBadge: false

    signal navigate(int index)
    signal openPalette()

    implicitWidth: Theme.railWidth
    color: Theme.surface
    border.color: Theme.borderSoft
    border.width: 0

    readonly property var items: [
        { label: "Run", icon: "play" },
        { label: "Review", icon: "list" },
        { label: "Quality", icon: "shield" },
        { label: "Log", icon: "terminal" },
        { label: "Settings", icon: "settings" }
    ]

    Rectangle {
        anchors.right: parent.right
        width: 1
        height: parent.height
        color: Theme.borderSoft
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: Theme.md
        anchors.bottomMargin: Theme.md
        spacing: Theme.xs

        Repeater {
            model: root.items

            delegate: Item {
                required property var modelData
                required property int index

                Layout.preferredWidth: 52
                Layout.preferredHeight: 52
                Layout.alignment: Qt.AlignHCenter

                readonly property bool isOn: root.currentIndex === index

                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radiusMd
                    color: parent.isOn ? Theme.accentSoft : (railMouse.containsMouse ? Theme.surfaceAlt : "transparent")
                }

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 3

                    Icon {
                        Layout.alignment: Qt.AlignHCenter
                        name: parent.parent.modelData.icon
                        color: parent.parent.isOn ? Theme.accent : Theme.textMuted
                        strokeWidth: 1.9
                        Layout.preferredWidth: 20
                        Layout.preferredHeight: 20
                    }

                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: parent.parent.modelData.label
                        color: parent.parent.isOn ? Theme.accent : Theme.textMuted
                        font.pixelSize: 10
                        font.bold: parent.parent.isOn
                    }
                }

                // Issue badge (Review) — warnings/errors waiting in the report.
                Rectangle {
                    visible: root.showBadge && index === 1 && root.reviewBadge > 0
                    x: parent.width - width + 2
                    y: -3
                    implicitWidth: Math.max(15, badgeLabel.implicitWidth + 8)
                    implicitHeight: 15
                    radius: 999
                    color: Theme.warning

                    Label {
                        id: badgeLabel
                        anchors.centerIn: parent
                        text: String(root.reviewBadge)
                        color: "#1A1200"
                        font.pixelSize: 9
                        font.bold: true
                    }
                }

                MouseArea {
                    id: railMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.navigate(index)
                }

                Accessible.role: Accessible.PageTab
                Accessible.name: modelData.label
                Accessible.selected: isOn
            }
        }

        Item { Layout.fillHeight: true }

        Item {
            Layout.preferredWidth: 52
            Layout.preferredHeight: 52
            Layout.alignment: Qt.AlignHCenter

            Rectangle {
                anchors.fill: parent
                radius: Theme.radiusMd
                color: paletteMouse.containsMouse ? Theme.surfaceAlt : "transparent"
            }

            ColumnLayout {
                anchors.centerIn: parent
                spacing: 3

                Icon {
                    Layout.alignment: Qt.AlignHCenter
                    name: "keyboard"
                    color: Theme.textMuted
                    Layout.preferredWidth: 20
                    Layout.preferredHeight: 20
                }

                Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: "Ctrl K"
                    color: Theme.textMuted
                    font.pixelSize: 10
                }
            }

            MouseArea {
                id: paletteMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.openPalette()
            }

            Accessible.role: Accessible.Button
            Accessible.name: "Open the command palette"
        }
    }
}
