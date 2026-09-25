import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// "Label ............ value" row used by the inspector / run-context cards.
//
// Neither half may truncate mid-word (UI review D4): "Network calls in Offline
// mode" used to render as "Network calls in Offl…". The key wraps to a second
// line instead of eliding, and the value — which *does* have to elide, because
// it is often an absolute path — carries its full text in a tooltip so nothing
// is unrecoverable.
RowLayout {
    id: root

    property string key: ""
    property string value: ""
    property color valueColor: Theme.text
    property bool mono: false
    // Callers with a wider column (the run-context card) can give the key more
    // room rather than relying on the wrap.
    property int keyWidth: 128

    spacing: 8
    Layout.fillWidth: true

    Label {
        text: root.key
        color: Theme.textMuted
        font.pixelSize: Theme.fontBody
        Layout.preferredWidth: root.keyWidth
        Layout.minimumWidth: 96
        wrapMode: Text.WordWrap
    }

    Label {
        id: valueLabel
        Layout.fillWidth: true
        text: root.value
        color: root.valueColor
        font.pixelSize: Theme.fontBody
        font.family: root.mono ? Theme.monoFont : Theme.uiFont
        horizontalAlignment: Text.AlignRight
        elide: Text.ElideMiddle

        ToolTip.text: root.value
        ToolTip.visible: valueHover.hovered && valueLabel.truncated
        ToolTip.delay: 400
        HoverHandler { id: valueHover }
    }
}
