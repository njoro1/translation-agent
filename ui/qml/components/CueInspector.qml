import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Master-detail inspector for one cue: timing (with explicit nudge controls —
// never silent retiming), the source line, the editable translation, its issue
// badges and the fix actions.
Item {
    id: root

    property int row: -1
    property int cueNumber: 0
    property int totalCues: 0
    property string filterLabel: ""

    signal navigate(int delta)

    implicitHeight: layout.implicitHeight

    readonly property var cue: {
        appBridge.cueEditedCount
        appBridge.resultReady
        if (root.row < 0)
            return null
        return appBridge.cueProxy.get(root.row)
    }

    readonly property bool hasCue: cue !== null && cue !== undefined
    readonly property real durationSec: hasCue
        ? Math.max(0, (cue.end_ms - cue.start_ms) / 1000.0) : 0
    readonly property int charCount: hasCue ? String(cue.text || "").replace(/\s/g, "").length : 0
    readonly property real cps: durationSec > 0 ? charCount / durationSec : 0

    function _msText(ms) {
        var total = Math.max(0, Math.round(ms))
        var h = Math.floor(total / 3600000)
        var m = Math.floor((total % 3600000) / 60000)
        var s = Math.floor((total % 60000) / 1000)
        var cs = Math.floor((total % 1000) / 10)
        function p(n) { return (n < 10 ? "0" : "") + n }
        return (h > 0 ? h + ":" : "") + p(m) + ":" + p(s) + "." + p(cs)
    }

    ColumnLayout {
        id: layout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Theme.sm

        // --- Navigation ---------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            AppButton {
                text: "Previous cue"
                small: true
                variant: "ghost"
                iconName: "chevron"
                enabled: root.row > 0
                onClicked: root.navigate(-1)
            }

            Item { Layout.fillWidth: true }

            Chip {
                text: root.hasCue ? (root.cueNumber + " / " + root.totalCues) : "—"
                mono: true
            }

            Item { Layout.fillWidth: true }

            AppButton {
                text: "Next cue"
                small: true
                variant: "ghost"
                iconName: "chevron"
                enabled: root.hasCue && root.row < root.totalCues - 1
                onClicked: root.navigate(1)
            }
        }

        Label {
            Layout.fillWidth: true
            visible: !root.hasCue
            text: appBridge.resultReady
                  ? "Select a cue in the table to inspect and edit it."
                  : "Run a translation, then pick a cue here to review it."
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
        }

        // --- Timing -------------------------------------------------------
        ColumnLayout {
            Layout.fillWidth: true
            visible: root.hasCue
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Label {
                    text: "In"
                    Layout.preferredWidth: 34
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                }
                CompactTextField {
                    Layout.fillWidth: true
                    height: Theme.controlHeightSmall
                    readOnly: true
                    text: root.hasCue ? root._msText(root.cue.start_ms) : ""
                    font.family: Theme.monoFont
                    label: "Cue start time"
                }
                AppButton {
                    text: "−"
                    small: true
                    enabled: root.hasCue
                    onClicked: appBridge.nudgeCueStart(root.row, -50)
                    Accessible.name: "Move the cue start 50 ms earlier"
                }
                AppButton {
                    text: "+"
                    small: true
                    enabled: root.hasCue
                    onClicked: appBridge.nudgeCueStart(root.row, 50)
                    Accessible.name: "Move the cue start 50 ms later"
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Label {
                    text: "Out"
                    Layout.preferredWidth: 34
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                }
                CompactTextField {
                    Layout.fillWidth: true
                    height: Theme.controlHeightSmall
                    readOnly: true
                    text: root.hasCue ? root._msText(root.cue.end_ms) : ""
                    font.family: Theme.monoFont
                    label: "Cue end time"
                }
                AppButton {
                    text: "−"
                    small: true
                    enabled: root.hasCue
                    onClicked: appBridge.nudgeCueEnd(root.row, -50)
                    Accessible.name: "Move the cue end 50 ms earlier"
                }
                AppButton {
                    text: "+"
                    small: true
                    enabled: root.hasCue
                    onClicked: appBridge.nudgeCueEnd(root.row, 50)
                    Accessible.name: "Move the cue end 50 ms later"
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Chip {
                    text: root.durationSec.toFixed(2) + " s"
                    mono: true
                }
                Chip {
                    text: root.cps.toFixed(1) + " cps"
                    mono: true
                    tone: {
                        if (!root.hasCue) return ""
                        var limits = appBridge.qualityLimits
                        if (root.cps >= limits.cpsError) return "err"
                        if (root.cps >= limits.cpsWarn) return "warn"
                        return "ok"
                    }
                }
                Item { Layout.fillWidth: true }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 1
                color: Theme.borderSoft
            }

            Label {
                text: "SOURCE"
                color: Theme.textMuted
                font.pixelSize: 10
                font.bold: true
                font.letterSpacing: 0.8
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: sourceLabel.implicitHeight + 18
                radius: Theme.radiusSm
                color: Theme.inset
                border.color: Theme.borderSoft
                border.width: 1

                Label {
                    id: sourceLabel
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    text: root.hasCue ? root.cue.source : ""
                    color: Theme.textDim
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                Label {
                    text: "TRANSLATION"
                    color: Theme.textMuted
                    font.pixelSize: 10
                    font.bold: true
                    font.letterSpacing: 0.8
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: root.charCount + " / " + appBridge.qualityLimits.charsWarn
                    color: root.charCount >= appBridge.qualityLimits.charsWarn ? Theme.warning : Theme.textMuted
                    font.pixelSize: Theme.fontTiny
                    font.family: Theme.monoFont
                }
            }

            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: 132
                clip: true

                TextArea {
                    id: editor
                    text: root.hasCue ? root.cue.text : ""
                    color: Theme.text
                    font.pixelSize: Theme.fontBody
                    wrapMode: TextArea.Wrap
                    selectByMouse: true
                    placeholderText: "Translation…"
                    background: Rectangle {
                        radius: Theme.radiusSm
                        color: Theme.inset
                        border.width: 1
                        border.color: editor.activeFocus ? Theme.accentLine : Theme.border
                    }
                    onActiveFocusChanged: {
                        if (!activeFocus && root.hasCue && text !== root.cue.text)
                            appBridge.setCueText(root.row, text)
                    }
                    Keys.onEscapePressed: {
                        text = root.hasCue ? root.cue.text : ""
                        focus = false
                    }
                }
            }

            // --- Issues + fixes -------------------------------------------
            Flow {
                Layout.fillWidth: true
                spacing: 6
                visible: root.hasCue && root.cue.tags !== undefined && root.cue.tags.length > 0

                Repeater {
                    model: root.hasCue ? root.cue.tags : []

                    delegate: Chip {
                        required property var modelData
                        text: String(modelData).replace(/_/g, " ")
                        tone: String(modelData).indexOf("_error") >= 0 || modelData === "empty_text" ? "err" : "warn"
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                AppButton {
                    text: "Auto-fix"
                    small: true
                    variant: "primary"
                    iconName: "zap"
                    enabled: root.hasCue
                    onClicked: appBridge.autoFixCue(root.row)
                    Accessible.name: "Strip leaked ASR tags and stray CJK from this cue"
                }
                AppButton {
                    text: "Revert cue"
                    small: true
                    iconName: "undo"
                    enabled: root.hasCue && root.cue.edited
                    onClicked: appBridge.revertCue(root.row)
                }
                Item { Layout.fillWidth: true }
                AppButton {
                    text: "Copy"
                    small: true
                    variant: "ghost"
                    iconName: "copy"
                    enabled: root.hasCue
                    onClicked: appBridge.copyToClipboard(root.cue.text)
                }
            }
        }
    }
}
