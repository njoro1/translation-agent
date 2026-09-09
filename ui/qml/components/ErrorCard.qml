import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Structured failure surface (UX review S-02).
//
// A failed run used to say only "Finished with errors (exit N). See the log."
// while the log drawer was collapsed, so the user had to discover a hidden
// control and read raw CLI output. This card states the cause in plain
// language and offers the single action most likely to fix it.
Rectangle {
    id: root

    Layout.fillWidth: true
    visible: appBridge.failureActive
    radius: Theme.radiusMd
    color: Theme.errorTint
    border.color: Theme.error
    border.width: 1

    readonly property string remedy: appBridge.failureRemediation

    readonly property string remedyLabel: {
        switch (root.remedy) {
        case "cloud": return "Open API settings"
        case "retry": return "Retry run"
        case "download_model": return "Download model"
        case "install_dependency": return "How to install"
        case "check_source": return "Check source"
        case "form": return "Back to Run"
        default: return "Show log"
        }
    }

    function applyRemedy() {
        switch (root.remedy) {
        case "cloud":
            appBridge.openAdvancedSettings()
            return
        case "retry":
            appBridge.runTranslation()
            return
        case "download_model":
            appBridge.downloadLocalModel()
            return
        case "install_dependency":
            appBridge.openDocumentation()
            return
        case "check_source":
        case "form":
            appBridge.requestTab(0)
            return
        default:
            appBridge.logVisible = true
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.md
        spacing: Theme.sm

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.sm

            Rectangle {
                implicitWidth: 22
                implicitHeight: 22
                radius: 11
                color: Theme.error

                Label {
                    anchors.centerIn: parent
                    text: "!"
                    color: Theme.accentText
                    font.pixelSize: Theme.fontLabel
                    font.bold: true
                }

                Accessible.ignored: true
            }

            Label {
                Layout.fillWidth: true
                text: appBridge.failureTitle
                color: Theme.error
                font.pixelSize: Theme.fontLabel
                font.bold: true
                wrapMode: Text.WordWrap

                Accessible.role: Accessible.StaticText
                Accessible.name: "Error: " + appBridge.failureTitle
            }

            Label {
                text: appBridge.failureCode
                color: Theme.textMuted
                font.pixelSize: 10
                font.bold: true
                font.letterSpacing: 0.8
            }
        }

        Label {
            Layout.fillWidth: true
            visible: appBridge.failureDetail !== "" && !detailsSwitch.checked
            text: appBridge.failureDetail
            color: Theme.text
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            font.family: "Consolas"
        }

        Label {
            Layout.fillWidth: true
            visible: detailsSwitch.checked
            text: appBridge.failureDetail
            color: Theme.text
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
            font.family: "Consolas"
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.sm

            Button {
                text: root.remedyLabel
                onClicked: root.applyRemedy()

                background: Rectangle {
                    radius: Theme.radiusSm
                    color: parent.hovered ? Theme.errorHover : Theme.error
                }
                contentItem: Label {
                    text: parent.text
                    color: Theme.accentText
                    font.pixelSize: Theme.fontSmall
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }

                Accessible.name: root.remedyLabel
                Accessible.role: Accessible.Button
            }

            Button {
                id: detailsSwitch
                checkable: true
                checked: false
                text: checked ? "Hide details" : "Show details"
                onClicked: checked = !checked

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

                Accessible.name: "Show error details"
                Accessible.role: Accessible.Button
            }

            Item { Layout.fillWidth: true }

            Button {
                text: "Dismiss"
                onClicked: appBridge.dismissFailure()

                background: Rectangle {
                    radius: Theme.radiusSm
                    color: parent.hovered ? Theme.surfaceAlt : "transparent"
                    border.color: Theme.border
                }
                contentItem: Label {
                    text: parent.text
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }

                Accessible.name: "Dismiss error"
                Accessible.role: Accessible.Button
            }
        }
    }
}
