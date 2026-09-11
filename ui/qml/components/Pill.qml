import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Status pill: a dot + a word, never colour alone.
// tone: ok | warn | err | info | acc | mute
Rectangle {
    id: root

    property string text: ""
    property string tone: "mute"
    property bool pulse: false

    readonly property color _fg: Theme.toneColor(tone)

    implicitWidth: row.implicitWidth + 20
    implicitHeight: 24
    radius: 999
    color: Theme.toneTint(tone)
    border.width: 1
    border.color: Theme.toneBorder(tone)

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 6

        Rectangle {
            Layout.preferredWidth: 6
            Layout.preferredHeight: 6
            radius: 3
            color: root._fg

            SequentialAnimation on opacity {
                running: root.pulse && !Theme.reducedMotion
                loops: Animation.Infinite
                NumberAnimation { to: 0.25; duration: 600 }
                NumberAnimation { to: 1.0; duration: 600 }
            }
        }

        Label {
            text: root.text
            color: root._fg
            font.pixelSize: Theme.fontSmall
            font.bold: true
        }
    }
}
