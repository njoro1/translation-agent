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
//
// Interaction (UI review 5.3): clicking a bar selects that cue, and dragging
// across the track selects a *range* of cues, which the caller turns into a
// table filter. The track used to be a static picture — it showed you where the
// problems were and then made you find them by hand.
ColumnLayout {
    id: root

    property var bars: []
    property var ruler: []
    property real playhead: -1
    property int selectedIndex: -1
    property int selectedCue: 0

    // Emitted with a 1-based cue number.
    signal barClicked(int cue)
    // Emitted with the first and last cue number the dragged span covers.
    signal rangeSelected(int firstCue, int lastCue)

    spacing: 6

    readonly property bool hasBars: bars !== undefined && bars !== null && bars.length > 0

    // Drag state, in track coordinates normalised to 0..1.
    property real dragStart: -1
    property real dragEnd: -1
    readonly property bool hasRange: dragStart >= 0 && dragEnd >= 0
    readonly property real rangeFrom: Math.min(dragStart, dragEnd)
    readonly property real rangeTo: Math.max(dragStart, dragEnd)

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

    // The cue whose bar covers `fraction` of the track, or 0.
    function _cueAt(fraction) {
        for (let i = 0; i < root.bars.length; i++) {
            const b = root.bars[i]
            if (fraction >= b.left && fraction <= b.left + b.width)
                return b.cue
        }
        return 0
    }

    // The cue-number span a dragged [from, to] range covers.
    function _cueSpan(from, to) {
        let first = 0, last = 0
        for (let i = 0; i < root.bars.length; i++) {
            const b = root.bars[i]
            if (b.left + b.width < from || b.left > to)
                continue
            if (first === 0 || b.cue < first) first = b.cue
            if (last === 0 || b.cue > last) last = b.cue
        }
        return { first: first, last: last }
    }

    function clearRange() {
        root.dragStart = -1
        root.dragEnd = -1
    }

    Item {
        Layout.fillWidth: true
        // No bars means no track: an empty 46px box under a "Timeline" header
        // is machinery pretending to be a chart (UI review D4).
        visible: root.hasBars
        Layout.preferredHeight: 46

        Rectangle {
            id: track
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

            // The dragged span, drawn behind the playhead.
            Rectangle {
                objectName: "timeline.rangeBand"
                visible: root.hasRange
                x: root.rangeFrom * parent.width
                width: Math.max(1, (root.rangeTo - root.rangeFrom) * parent.width)
                height: parent.height
                color: Theme.accentSoft
                border.width: 1
                border.color: Theme.accentLine
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

        MouseArea {
            id: scrub
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor

            // Below this, a press is a click on a bar rather than a drag.
            readonly property int dragThreshold: 4

            function fraction(x) {
                return Math.max(0, Math.min(1, x / Math.max(1, width)))
            }

            onPressed: (mouse) => {
                root.dragStart = fraction(mouse.x)
                root.dragEnd = root.dragStart
            }
            onPositionChanged: (mouse) => {
                if (pressed)
                    root.dragEnd = fraction(mouse.x)
            }
            onReleased: (mouse) => {
                const travelled = Math.abs(root.dragEnd - root.dragStart) * width
                if (travelled < dragThreshold) {
                    root.clearRange()
                    const cue = root._cueAt(root.dragStart)
                    if (cue > 0)
                        root.barClicked(cue)
                    return
                }
                const span = root._cueSpan(root.rangeFrom, root.rangeTo)
                if (span.first > 0 && span.last > 0)
                    root.rangeSelected(span.first, span.last)
                else
                    root.clearRange()
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
