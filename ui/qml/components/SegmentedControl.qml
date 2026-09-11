import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Segmented control (the mockup's `.seg`): a row of mutually exclusive options
// inside one inset track.
//
//   SegmentedControl {
//       options: [{ id: "dark", label: "Dark" }, { id: "light", label: "Light" }]
//       current: appBridge.themeName
//       onActivated: (id) => appBridge.themeName = id
//   }
Item {
    id: root

    property var options: []
    property string current: ""

    signal activated(string id)

    implicitWidth: track.implicitWidth + 6
    implicitHeight: Theme.controlHeight

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusSm
        color: Theme.inset
        border.color: Theme.border
        border.width: 1
    }

    RowLayout {
        id: track
        anchors.fill: parent
        anchors.margins: 3
        spacing: 3

        Repeater {
            model: root.options

            delegate: Rectangle {
                id: seg
                required property var modelData

                readonly property bool isOn: root.current === modelData.id

                Layout.fillHeight: true
                implicitWidth: segLabel.implicitWidth + 24
                radius: Theme.radiusXs
                color: seg.isOn ? Theme.accent
                                : (segHover.hovered ? Theme.surfaceAlt : "transparent")

                Label {
                    id: segLabel
                    anchors.centerIn: parent
                    text: seg.modelData.label
                    color: seg.isOn ? Theme.accentInk : Theme.textDim
                    font.pixelSize: Theme.fontSmall
                    font.bold: seg.isOn
                }

                HoverHandler { id: segHover }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.activated(seg.modelData.id)
                }

                Accessible.role: Accessible.RadioButton
                Accessible.name: seg.modelData.label
                Accessible.checked: seg.isOn
                Accessible.onPressAction: root.activated(seg.modelData.id)
            }
        }
    }
}
