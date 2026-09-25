import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Danger zone (UI review 5.6).
//
// `Clear stored settings` used to sit at equal visual weight, on the same row,
// beside the benign `Open debug.log` — a footgun next to a safe action. It is
// now spatially separated, styled as destructive, and gated behind a typed
// confirmation that names what will be erased.
Rectangle {
    id: root

    property string title: "Danger zone"
    property string description: ""
    property string actionLabel: "Clear stored settings"
    // The word the user must type. Deliberately a word they cannot type by
    // accident while clicking around.
    property string confirmWord: "RESET"

    signal confirmed()

    Layout.fillWidth: true
    implicitHeight: body.implicitHeight + 26
    radius: Theme.radiusMd
    color: Theme.errorTint
    border.width: 1
    border.color: Qt.rgba(Theme.error.r, Theme.error.g, Theme.error.b, 0.45)

    readonly property bool armed: confirmField.text.trim().toUpperCase() === root.confirmWord

    ColumnLayout {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 13
        spacing: 9

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Icon { name: "alert"; width: 15; height: 15; color: Theme.error }

            Label {
                Layout.fillWidth: true
                text: root.title
                color: Theme.error
                font.pixelSize: Theme.fontBody
                font.bold: true
            }
        }

        Label {
            Layout.fillWidth: true
            visible: root.description !== ""
            text: root.description
            color: Theme.textDim
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
        }

        Label {
            Layout.fillWidth: true
            text: "Type " + root.confirmWord + " to confirm."
            color: Theme.textMuted
            font.pixelSize: Theme.fontTiny
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            CompactTextField {
                id: confirmField
                Layout.preferredWidth: 160
                placeholderText: root.confirmWord
                label: "Type " + root.confirmWord + " to confirm"
                onAccepted: if (root.armed) root.fire()
            }

            AppButton {
                text: root.actionLabel
                small: true
                variant: "danger"
                iconName: "x"
                enabled: root.armed
                onClicked: root.fire()
                Accessible.name: root.actionLabel
            }

            Item { Layout.fillWidth: true }
        }
    }

    function fire() {
        if (!root.armed)
            return
        root.confirmed()
        confirmField.text = ""
    }
}
