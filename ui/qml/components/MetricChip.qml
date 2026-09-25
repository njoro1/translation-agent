import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// One quality metric, label-first (UI review D4 / 5.11).
//
// The old `StatTile` uppercased the label at 10px inside a fixed-width cell and
// elided it, which turned "Max line chars" into "MAX LINE CH…" and "Strict
// gate" into whatever was left. The words were never the defect — the tile
// was. Here the label wraps to two lines at its natural case, and the value
// carries the tone.
//
// `hint` is the one-line explanation, shown on hover. `breakdown` is an
// optional list of `{ k, v }` rows revealed on click, for metrics that have a
// real decomposition. A chip with no breakdown is inert: no pointer cursor, no
// click handler, so it cannot pretend to be interactive.
Rectangle {
    id: root

    property string label: ""
    property string value: ""
    property string tone: ""
    property string hint: ""
    property var breakdown: []

    readonly property bool hasBreakdown: {
        if (!breakdown || breakdown.length === undefined) return false
        return breakdown.length > 0
    }
    readonly property color valueColor: {
        if (tone === "ok") return Theme.success
        if (tone === "warn") return Theme.warning
        if (tone === "err") return Theme.error
        if (tone === "acc") return Theme.accent
        if (tone === "mute") return Theme.textMuted
        return Theme.text
    }

    signal clicked()

    implicitHeight: 62
    radius: Theme.radiusMd
    color: chipHover.hovered && root.hasBreakdown ? Theme.surfaceAlt : Theme.surfaceRaised
    border.width: 1
    border.color: root.hasBreakdown && root.breakdownOpen
                  ? Theme.accentLine : Theme.borderSoft

    // The breakdown is a popup rather than an inline expansion: the metric row
    // is a fixed-height band, and growing one chip would push the seven-card
    // grid below it down by a line.
    property bool breakdownOpen: false

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 2

        Label {
            Layout.fillWidth: true
            text: root.label
            color: Theme.textMuted
            font.pixelSize: Theme.fontTiny
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight      // only if a two-line wrap is still too tall
        }

        Label {
            Layout.fillWidth: true
            text: root.value
            color: root.valueColor
            font.pixelSize: Theme.fontH2
            font.bold: true
            elide: Text.ElideRight
        }
    }

    HoverHandler { id: chipHover }

    MouseArea {
        anchors.fill: parent
        enabled: root.hasBreakdown
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            root.breakdownOpen = !root.breakdownOpen
            root.clicked()
        }
    }

    ToolTip.text: root.hint
    ToolTip.visible: root.hint !== "" && chipHover.hovered
    ToolTip.delay: 400

    Popup {
        id: breakdownPopup
        visible: root.breakdownOpen
        x: 0
        y: root.height + 4
        width: Math.max(root.width, 200)
        padding: 10
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            radius: Theme.radiusMd
            color: Theme.surfaceRaised
            border.width: 1
            border.color: Theme.border
        }

        contentItem: ColumnLayout {
            spacing: 4

            Repeater {
                model: root.breakdown

                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 12

                    Label {
                        Layout.fillWidth: true
                        text: modelData.k
                        color: Theme.textDim
                        font.pixelSize: Theme.fontSmall
                        wrapMode: Text.WordWrap
                    }
                    Label {
                        text: String(modelData.v)
                        color: Theme.text
                        font.pixelSize: Theme.fontSmall
                        font.family: Theme.monoFont
                    }
                }
            }
        }

        onClosed: root.breakdownOpen = false
    }

    Accessible.role: Accessible.StaticText
    Accessible.name: root.label + ": " + root.value
}
