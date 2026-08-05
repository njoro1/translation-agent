import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "views"
import "components"

ApplicationWindow {
    id: window

    width: 1360
    height: 880
    minimumWidth: 1120
    minimumHeight: 760
    visible: true
    title: "Translation Agent"
    color: "#050816"

    property string currentView: "dashboard"

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#050816" }
            GradientStop { position: 0.45; color: "#0b1120" }
            GradientStop { position: 1.0; color: "#09090b" }
        }
    }

    header: Rectangle {
        height: 68
        color: "#0b1220"
        border.color: "#1f2937"
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            spacing: 16

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
                    font.pixelSize: 18
                    font.bold: true
                }
            }

            Item {
                Layout.fillWidth: true
            }

            Rectangle {
                radius: 999
                color: appBridge.isRunning ? "#312e81" : "#111827"
                border.color: appBridge.isRunning ? "#6366f1" : "#27272a"
                border.width: 1
                implicitHeight: 36
                implicitWidth: statusRow.implicitWidth + 24

                RowLayout {
                    id: statusRow
                    anchors.centerIn: parent
                    spacing: 10

                    Rectangle {
                        implicitWidth: 10
                        implicitHeight: 10
                        radius: 5
                        color: appBridge.isRunning ? "#22c55e" : "#64748b"

                        Behavior on color {
                            ColorAnimation { duration: 180 }
                        }
                    }

                    Label {
                        text: appBridge.isRunning ? "Pipeline active" : "Ready"
                        color: "#e2e8f0"
                        font.pixelSize: 12
                        font.bold: true
                    }
                }
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            Layout.fillHeight: true
            currentView: window.currentView
            onViewRequested: (view) => window.currentView = view
        }

        StackView {
            id: stackView
            Layout.fillWidth: true
            Layout.fillHeight: true
            initialItem: dashboardView

            // Instant view switching — replaces the default swipe/slide animations
            pushEnter: Transition {}
            pushExit: Transition {}
            popEnter: Transition {}
            popExit: Transition {}
            replaceEnter: Transition {}
            replaceExit: Transition {}
        }
    }

    Component {
        id: dashboardView
        DashboardView {}
    }

    Component {
        id: settingsView
        SettingsView {}
    }

    Connections {
        target: window
        function onCurrentViewChanged() {
            if (currentView === "settings") {
                stackView.replace(settingsView)
            } else {
                stackView.replace(dashboardView)
            }
        }
    }
}
