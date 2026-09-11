import QtQuick
import QtQuick.Controls
import ".."

// Labelled checkbox (square, check glyph). Same contract as AppSwitch.
Item {
    id: root

    property string text: ""
    property bool checked: false
    property string accessibleName: text

    signal toggled(bool checked)

    implicitWidth: box.width + (text !== "" ? 9 + label.implicitWidth : 0)
    implicitHeight: Math.max(18, label.implicitHeight)
    opacity: enabled ? 1.0 : 0.45
    activeFocusOnTab: true

    function _toggle() {
        root.checked = !root.checked
        root.toggled(root.checked)
    }

    Rectangle {
        id: box
        width: 16
        height: 16
        radius: 5
        anchors.verticalCenter: parent.verticalCenter
        color: root.checked ? Theme.accent : "transparent"
        border.width: root.checked ? 0 : 1.5
        border.color: Theme.borderStrong

        Icon {
            anchors.centerIn: parent
            visible: root.checked
            name: "check"
            color: "#FFFFFF"
            strokeWidth: 2.4
            width: 11
            height: 11
        }
    }

    Label {
        id: label
        anchors.left: box.right
        anchors.leftMargin: 9
        anchors.verticalCenter: parent.verticalCenter
        visible: root.text !== ""
        text: root.text
        color: Theme.textDim
        font.pixelSize: Theme.fontBody
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root._toggle()
    }

    Keys.onSpacePressed: root._toggle()
    Keys.onReturnPressed: root._toggle()

    Accessible.role: Accessible.CheckBox
    Accessible.name: root.accessibleName
    Accessible.checked: root.checked
    Accessible.focusable: true
}
