import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Cue timeline: one bar per cue, positioned by start time and sized by duration.
// ``bars`` is a list of {left: 0..1, width: 0..1, tone: ""|"ok"|"warn"|"err",
// cue: <1-based cue number>}.
//
// Highlighting works by ``selectedCue`` (a cue number, robust when the table is
// filtered) or by ``selectedIndex`` (a raw bar index).
ColumnLayout {
    id: root

    property var bars: []
    property var ruler: []
    property real playhead: -1
    property int selectedIndex: -1
    property int selectedCue: 0

    spacing: 6

    function _isSelected(index, modelData) {
        if (root.selectedCue > 0 && modelData !== undefined && modelData.cue !== undefined)
            return modelData.cue === root.selectedCue
        return index === root.selectedIndex
    }

    function _barColor(tone) {
        if (tone === "err") return Theme.error
        if (tone === "warn") return Theme.warning
        if (tone === "ok") return Theme.success
        return Theme.accent
    }

    Item {
        Layout.fillWidth: true
        Layout.preferredHeight: 46

        Rectangle {
            anchors.fill: parent
            radius: Theme.radiusSm
            color: Theme.inset
            border.color: Theme.borderSoft
            border.width: 1
            clip: true

            Repeater {
                model: root.bars

                delegate: Rectangle {
                    required property var modelData
                    required property int index

                    x: Math.max(0, modelData.left * parent.width)
                    width: Math.max(2, modelData.width * parent.width)
                    y: 8
                    height: 12
                    radius: 3
                    color: root._barColor(modelData.tone)
                    opacity: root._barColor(modelData.tone) === Theme.accent ? 0.5 : 0.75
                    border.width: root._isSelected(index, modelData) ? 1.5 : 0
                    border.color: Theme.text
                }
            }

            Rectangle {
                visible: root.playhead >= 0
                x: Math.max(0, Math.min(parent.width - 2, root.playhead * parent.width))
                width: 2
                height: parent.height
                color: Theme.text
                opacity: 0.85
            }
        }
    }

    RowLayout {
        visible: root.ruler.length > 0
        Layout.fillWidth: true
        spacing: 0

        Repeater {
            model: root.ruler

            delegate: Label {
                required property var modelData
                Layout.fillWidth: true
                text: String(modelData)
                color: Theme.textMuted
                font.pixelSize: 10
                font.family: Theme.monoFont
                horizontalAlignment: Text.AlignLeft
            }
        }
    }
}
