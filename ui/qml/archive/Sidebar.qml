import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    // Currently selected view key: "dashboard" | "settings".
    property string currentView: "dashboard"
    // Emitted when the user picks a nav item.
    signal viewRequested(string view)

    implicitWidth: 240
    color: "#0b1220"
    border.color: "#1f2937"
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 20

        // Brand
        RowLayout {
            spacing: 12

            Rectangle {
                implicitWidth: 40
                implicitHeight: 40
                radius: 12
                color: "#312e81"

                Label {
                    anchors.centerIn: parent
                    text: "T"
                    color: "#ffffff"
                    font.pixelSize: 18
                    font.bold: true
                }
            }

            ColumnLayout {
                spacing: 2

                Label {
                    text: "Translation Agent"
                    color: "#f8fafc"
                    font.pixelSize: 14
                    font.bold: true
                }

                Label {
                    text: "Desktop pipeline"
                    color: "#94a3b8"
                    font.pixelSize: 11
                }
            }
        }

        // Navigation
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6

            Label {
                text: "NAVIGATE"
                color: "#64748b"
                font.pixelSize: 10
                font.bold: true
                Layout.leftMargin: 8
            }

            Repeater {
                model: [
                    { key: "dashboard", label: "Dashboard" },
                    { key: "settings", label: "Settings" }
                ]

                delegate: Rectangle {
                    required property string key
                    required property string label

                    Layout.fillWidth: true
                    implicitHeight: 44
                    radius: 12
                    color: root.currentView === key ? "#1e293b" : "transparent"

                    Behavior on color {
                        ColorAnimation { duration: 140 }
                    }

                    Label {
                        anchors.left: parent.left
                        anchors.leftMargin: 16
                        anchors.verticalCenter: parent.verticalCenter
                        text: parent.label
                        color: root.currentView === key ? "#f8fafc" : "#94a3b8"
                        font.pixelSize: 14
                        font.bold: root.currentView === key
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.viewRequested(key)
                    }
                }
            }
        }

        Item { Layout.fillHeight: true }
    }
}
