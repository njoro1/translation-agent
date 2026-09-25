import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// The app's one empty-screen pattern (UI review D4 / T-4.6).
//
// An empty screen shows a prompt and nothing else. It must not render the
// machinery it would use once there is data: a ghosted thresholds table
// advertising `warn 18 · error 22` against zero cues, a toolbar of disabled
// buttons, an empty timeline box. Those read as "the app is broken", and every
// number in them is a lie. The Log screen got this right first, so the other
// screens adopt its shape rather than inventing a second one.
//
// The prompt names the next action, because "no data" is not a state a user
// can act on.
Item {
    id: root

    property string iconName: "info"
    property string title: ""
    property string body: ""
    property string actionLabel: ""
    property string actionIcon: "play"

    signal actionTriggered()

    implicitWidth: col.implicitWidth
    implicitHeight: col.implicitHeight

    ColumnLayout {
        id: col
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        width: root.width > 0 ? root.width : implicitWidth
        spacing: Theme.sm

        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            implicitWidth: 44
            implicitHeight: 44
            radius: 22
            color: Theme.surfaceRaised
            border.width: 1
            border.color: Theme.borderSoft

            Icon {
                anchors.centerIn: parent
                name: root.iconName
                width: 20
                height: 20
                color: Theme.textMuted
            }
        }

        Label {
            Layout.fillWidth: true
            Layout.topMargin: Theme.xs
            text: root.title
            color: Theme.text
            font.pixelSize: Theme.fontTitle
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        Label {
            Layout.fillWidth: true
            visible: root.body !== ""
            text: root.body
            color: Theme.textMuted
            font.pixelSize: Theme.fontBody
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }

        AppButton {
            objectName: "emptyState.action"
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: Theme.xs
            visible: root.actionLabel !== ""
            text: root.actionLabel
            iconName: root.actionIcon
            onClicked: root.actionTriggered()
        }
    }

    Accessible.role: Accessible.StaticText
    Accessible.name: root.body !== "" ? root.title + ". " + root.body : root.title
}
