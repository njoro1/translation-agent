import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Small bar histogram. ``bars`` is a list of {v: 0..1, tone: "acc"|"warn"|"ok"|""}
// and ``labels`` is an optional list of evenly spread axis labels.
ColumnLayout {
    id: root

    property var bars: []
    property var labels: []
    property real plotHeight: 92
    property bool showLabels: true

    spacing: 6

    function _barColor(tone) {
        if (tone === "warn") return Theme.warning
        if (tone === "ok") return Theme.success
        if (tone === "err") return Theme.error
        if (tone === "mute") return Theme.surfaceRaised
        return Theme.accent
    }

    Item {
        Layout.fillWidth: true
        Layout.preferredHeight: root.plotHeight

        Row {
            id: row
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: root.plotHeight
            spacing: 3

            Repeater {
                model: root.bars

                delegate: Item {
                    required property var modelData
                    required property int index

                    width: Math.max(2, (row.width - (root.bars.length - 1) * row.spacing)
                                      / Math.max(1, root.bars.length))
                    height: row.height

                    Rectangle {
                        anchors.bottom: parent.bottom
                        width: parent.width
                        height: Math.max(2, parent.height * Math.max(0.02, Math.min(1, modelData.v)))
                        radius: 3
                        color: root._barColor(modelData.tone)
                        opacity: modelData.tone === "" || modelData.tone === undefined ? 0.55 : 0.9
                    }
                }
            }
        }
    }

    RowLayout {
        visible: root.showLabels && root.labels.length > 0
        Layout.fillWidth: true
        spacing: 0

        Repeater {
            model: root.labels

            delegate: Label {
                required property var modelData
                Layout.fillWidth: true
                text: String(modelData)
                color: Theme.textMuted
                font.pixelSize: 10
                font.family: Theme.monoFont
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }
}
