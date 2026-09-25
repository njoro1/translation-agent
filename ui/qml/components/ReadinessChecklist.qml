import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Pre-run readiness checklist, rendered from ``appBridge.readinessRows``.
//
// The state machine lives in Python (testable, with real `na` and `unchecked`
// states) — this component is only a renderer. A row that can never fail
// teaches users to ignore the checklist, so nothing here is hardcoded green.
//
// Row status uses ``StatusMark`` so the five facts (ok / todo / na /
// unchecked / error) look different from each other. The previous version
// mapped both `n/a` and `unchecked` to a grey minus, and bolded the row label
// when the state was `ok` — bolding users read as "blocker" (UI review 2.1,
// 6.4). Both are gone.
ColumnLayout {
    id: root

    spacing: 2

    readonly property var rows: appBridge.readinessRows

    // "2 of 3 actionable · 1 n/a" — the denominator counts real checks only,
    // so it always equals the number of actionable rows on screen.
    readonly property string scoreText: {
        var actionable = 0, ready = 0, na = 0
        for (var i = 0; i < rows.length; i++) {
            if (rows[i].actionable) {
                actionable++
                if (rows[i].state === "ok") ready++
            } else if (rows[i].state === "na") {
                na++
            }
        }
        var text = ready + " of " + actionable + " actionable"
        if (na > 0) text += "  \u00b7  " + na + " n/a"
        return text
    }

    Repeater {
        model: root.rows

        delegate: Rectangle {
            id: row
            required property var modelData

            readonly property bool isNa: modelData.state === "na"
            readonly property bool isUnchecked: modelData.state === "unchecked"
            // Only real checks can be "not satisfied"; na/unchecked are facts.
            readonly property bool isBlocking: modelData.state === "todo"

            Layout.fillWidth: true
            implicitHeight: rowLayout.implicitHeight + 16
            radius: Theme.radiusSm
            color: rowHover.hovered ? Theme.surfaceAlt : "transparent"

            RowLayout {
                id: rowLayout
                anchors.fill: parent
                anchors.leftMargin: 9
                anchors.rightMargin: 9
                spacing: 10

                StatusMark {
                    Layout.alignment: Qt.AlignTop
                    status: row.modelData.state
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1

                    Label {
                        Layout.fillWidth: true
                        text: modelData.label
                        // No ad-hoc bolding: the StatusMark carries the state.
                        color: row.isNa || row.isUnchecked ? Theme.textMuted
                                                           : Theme.text
                        font.pixelSize: Theme.fontBody
                        wrapMode: Text.WordWrap
                    }

                    Label {
                        Layout.fillWidth: true
                        visible: modelData.hint !== ""
                        text: modelData.hint
                        color: row.isBlocking ? Theme.warning : Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        wrapMode: Text.WordWrap
                    }
                }

                // The mode-dependency is spelled out rather than left as a bare
                // dash, so "n/a" always has a readable subject.
                Label {
                    visible: row.isNa
                    text: "n/a"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                }
                Label {
                    visible: row.isUnchecked
                    text: "not checked"
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                }
            }

            HoverHandler { id: rowHover }

            Accessible.role: Accessible.StaticText
            Accessible.name: {
                var word = "needs attention"
                if (modelData.state === "ok") word = "ready"
                else if (modelData.state === "na") word = "not applicable"
                else if (modelData.state === "unchecked") word = "not checked yet"
                return modelData.label + ": " + word
            }
        }
    }
}
