import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Small metadata chip. tone: "" | acc | ok | warn | err | info
Rectangle {
    id: root

    property string text: ""
    property string tone: ""
    property string iconName: ""
    property bool mono: false

    readonly property color _fg: tone === "" ? Theme.textDim : Theme.toneColor(tone)

    implicitWidth: row.implicitWidth + 16
    implicitHeight: 22
    radius: Theme.radiusXs
    color: tone === "" ? Theme.surfaceRaised : Theme.toneTint(tone)
    border.width: 0

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 5

        Icon {
            visible: root.iconName !== ""
            name: root.iconName
            color: root._fg
            Layout.preferredWidth: 11
            Layout.preferredHeight: 11
        }

        Label {
            text: root.text
            color: root._fg
            font.pixelSize: root.mono ? Theme.fontTiny : Theme.fontSmall
            font.family: root.mono ? Theme.monoFont : Theme.uiFont
            font.bold: true
        }
    }
}
