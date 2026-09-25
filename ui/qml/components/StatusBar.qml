import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Bottom status bar (UI review 3.2).
//
// Each item is EITHER a button (hover/press affordance) OR a hint (flat,
// non-interactive). The old bar mixed clickable chips with legend chips
// indistinguishably, and repeated the Log/Commands entry points the left rail
// and the palette already own.
//
// The bar is now status + contextual hints only. Navigation is the rail's job;
// launching things is the palette's job.
Rectangle {
    id: root

    objectName: "chrome.statusBar"

    property int currentIndex: 0

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
            return [["\u2191 \u2193", "Navigate"], ["Ctrl S", "Save"], ["Ctrl F", "Search"]]
        if (currentIndex === 2)
            return [["Ctrl L", "Log"], ["Ctrl K", "Commands"]]
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
        anchors.rightMargin: 14
        spacing: 10

        // --- Status (read-only) ---------------------------------------------
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

        // --- Hints (flat, non-interactive, no border, no hover) --------------
        // The key cap keeps the monospace chip look because it reads as a key,
        // but nothing here responds to the pointer, and the leading "Shortcuts"
        // label makes that unambiguous.
        Label {
            text: "Shortcuts"
            color: Theme.textMuted
            font.pixelSize: 10
            font.letterSpacing: 0.6
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
                    // Flat surface, no border: a legend, not a button.
                    color: Theme.surfaceAlt

                    Label {
                        id: hintText
                        anchors.centerIn: parent
                        text: modelData[0]
                        color: Theme.textMuted
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
    }
}
