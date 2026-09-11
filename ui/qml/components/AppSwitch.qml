import QtQuick
import QtQuick.Controls
import ".."

// Labelled switch. Emits ``toggled(checked)`` so the caller can push the value
// into the bridge; ``checked`` is normally bound to a bridge property.
Item {
    id: root

    property string text: ""
    property bool checked: false
    property string accessibleName: text

    signal toggled(bool checked)

    implicitWidth: track.width + (text !== "" ? 9 + label.implicitWidth : 0)
    implicitHeight: Math.max(18, label.implicitHeight)
    opacity: enabled ? 1.0 : 0.45
    activeFocusOnTab: true

    function _toggle() {
        root.checked = !root.checked
        root.toggled(root.checked)
    }

    Rectangle {
        id: track
        width: 32
        height: 18
        radius: 9
        anchors.verticalCenter: parent.verticalCenter
        color: root.checked ? Theme.accent : Theme.borderStrong
        Behavior on color { ColorAnimation { duration: Theme.reducedMotion ? 0 : 140 } }

        Rectangle {
            width: 14
            height: 14
            radius: 7
            y: 2
            x: root.checked ? parent.width - width - 2 : 2
            color: "#FFFFFF"
            Behavior on x { NumberAnimation { duration: Theme.reducedMotion ? 0 : 140 } }
        }
    }

    Label {
        id: label
        anchors.left: track.right
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
