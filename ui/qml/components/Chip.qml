import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Small metadata chip. tone: "" | acc | ok | warn | err | info
//
// `clickable` turns a chip into a link (the cue inspector's quality flags, which
// deep-link into the Quality issue list). It is opt-in so the many decorative
// chips in the app cannot accidentally acquire a pointer cursor and a hit area.
Rectangle {
    id: root

    property string text: ""
    property string tone: ""
    property string iconName: ""
    property bool mono: false
    property bool clickable: false

    signal clicked()

    readonly property color _fg: tone === "" ? Theme.textDim : Theme.toneColor(tone)

    implicitWidth: row.implicitWidth + 16
    implicitHeight: 22
    radius: Theme.radiusXs
    color: root.clickable && chipHover.hovered
           ? Theme.surfaceAlt
           : (tone === "" ? Theme.surfaceRaised : Theme.toneTint(tone))
    border.width: root.clickable ? 1 : 0
    border.color: root.clickable ? Theme.borderSoft : "transparent"

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

    HoverHandler { id: chipHover; enabled: root.clickable }

    MouseArea {
        anchors.fill: parent
        enabled: root.clickable
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }

    Accessible.role: root.clickable ? Accessible.Link : Accessible.StaticText
}
