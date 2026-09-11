import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Bottom status bar: one-line state + the log ticker + the shortcuts that matter.
Rectangle {
    id: root

    property int currentIndex: 0
    signal openLog()

    implicitHeight: Theme.statusbarHeight
    color: Theme.surface
    border.color: Theme.borderSoft

    readonly property string stateWord: {
        if (appBridge.statusState === "done") return "Done"
        if (appBridge.statusState === "failed") return "Failed"
        if (appBridge.statusState === "cancelled") return "Cancelled"
        if (appBridge.statusState === "validating") return "Validating"
        if (appBridge.statusState === "running") return "Running"
        return "Idle"
    }

    readonly property color stateColor: {
        if (appBridge.statusState === "done") return Theme.success
        if (appBridge.statusState === "failed") return Theme.error
        if (appBridge.statusState === "cancelled") return Theme.warning
        if (appBridge.isRunning) return Theme.accent
        return Theme.textMuted
    }

    readonly property var hints: {
        if (currentIndex === 0)
            return [["Ctrl Enter", "Run"], ["Ctrl .", "Cancel"], ["Ctrl K", "Commands"]]
        if (currentIndex === 1)
            return [["↑ ↓", "Navigate"], ["Ctrl S", "Save"], ["Ctrl F", "Search"]]
        if (currentIndex === 2)
            return [["Ctrl L", "Log"], ["Ctrl K", "Commands"]]
        if (currentIndex === 3)
            return [["Ctrl K", "Commands"]]
        return [["Ctrl K", "Commands"]]
    }

    Rectangle {
        anchors.top: parent.top
        width: parent.width
        height: 1
        color: Theme.borderSoft
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 10
        spacing: 10

        Rectangle {
            Layout.preferredWidth: 6
            Layout.preferredHeight: 6
            radius: 3
            color: root.stateColor

            SequentialAnimation on opacity {
                running: appBridge.isRunning && !Theme.reducedMotion
                loops: Animation.Infinite
                NumberAnimation { to: 0.25; duration: 600 }
                NumberAnimation { to: 1.0; duration: 600 }
            }
        }

        Label {
            text: root.stateWord
            color: Theme.textDim
            font.pixelSize: Theme.fontSmall
            font.bold: true
        }

        Label {
            Layout.fillWidth: true
            text: appBridge.statusMessage
            color: Theme.textMuted
            font.pixelSize: Theme.fontTiny
            font.family: Theme.monoFont
            elide: Text.ElideRight
        }

        Repeater {
            model: root.hints

            delegate: RowLayout {
                required property var modelData
                spacing: 5

                Rectangle {
                    implicitWidth: hintText.implicitWidth + 12
                    implicitHeight: 18
                    radius: 5
                    color: Theme.surfaceRaised
                    border.color: Theme.border
                    border.width: 1

                    Label {
                        id: hintText
                        anchors.centerIn: parent
                        text: modelData[0]
                        color: Theme.textDim
                        font.pixelSize: 10
                        font.family: Theme.monoFont
                    }
                }

                Label {
                    text: modelData[1]
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontTiny
                }
            }
        }

        AppButton {
            text: "Log"
            small: true
            variant: "ghost"
            iconName: "terminal"
            onClicked: root.openLog()
            Accessible.name: "Open the log"
        }
    }
}
