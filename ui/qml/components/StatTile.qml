import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Stat tile: one big number over a small uppercase key.
// tone: "" | acc | ok | warn | err | mute
Rectangle {
    id: root

    property string value: ""
    property string label: ""
    property string tone: ""
    property string hint: ""

    readonly property color _valueColor: {
        if (tone === "ok") return Theme.success
        if (tone === "warn") return Theme.warning
        if (tone === "err") return Theme.error
        if (tone === "acc") return Theme.accent
        if (tone === "mute") return Theme.textMuted
        return Theme.text
    }

    Layout.fillWidth: true
    implicitHeight: 58
    radius: Theme.radiusMd
    color: Theme.surfaceAlt
    border.color: Theme.borderSoft
    border.width: 1

    ColumnLayout {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 1

        Label {
            Layout.fillWidth: true
            text: root.value
            color: root._valueColor
            font.pixelSize: Theme.fontH2
            font.bold: true
            font.family: Theme.uiFont
            elide: Text.ElideRight
        }

        Label {
            Layout.fillWidth: true
            text: root.label.toUpperCase()
            color: Theme.textMuted
            font.pixelSize: 10
            font.bold: true
            font.letterSpacing: 0.6
            elide: Text.ElideRight
        }
    }

    ToolTip.text: root.hint
    ToolTip.visible: hint !== "" && hoverHandler.hovered
    ToolTip.delay: 400
    HoverHandler { id: hoverHandler }
}
