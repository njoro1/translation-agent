import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."
import "../components"

// Review screen: filter + cue table + timeline on the left, master-detail cue
// inspector on the right. Every row is editable in place; the inspector adds
// explicit timing nudges, tag stripping and revert.
Item {
    id: root

    property int selectedRow: -1
    property string replaceNotice: ""

    // 1-based cue number of the selected row (a filtered table's row index is
    // not the cue number, so the inspector and the timeline use this).
    readonly property int selectedCueNumber: {
        appBridge.cueEditedCount
        if (root.selectedRow < 0)
            return 0
        const data = appBridge.cueProxy.get(root.selectedRow)
        return data && data.index ? data.index : 0
    }

    signal navigateRequested(int page)

    function focusSearch() {
        table.focusSearch()
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16
        // Toolbars, timeline and inspector exist only when there is a result.
        // Before that they were a ghosted grid of disabled controls (UI review
        // D4 / T-4.6).
        visible: appBridge.resultReady

        // =========================================================== LEFT ==
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 420
            Layout.fillHeight: true
            spacing: 16

            AppCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: "Cues"
                headerExtra: [
                    Chip {
                        text: appBridge.qualityTotalCues + " cues"
                        mono: true
                    },
                    Chip {
                        visible: appBridge.cueEditedCount > 0
                        text: appBridge.cueEditedCount + " edited"
                        tone: "acc"
                        mono: true
                    },
                    AppButton {
                        text: "Open file"
                        small: true
                        variant: "ghost"
                        iconName: "external"
                        enabled: appBridge.canOpenOutputFolder
                        onClicked: appBridge.openInExternalEditor()
                        Accessible.name: "Open the output file in an external editor"
                    },
                    // Edits live in the model until they are written back. The
                    // bridge slot has existed all along (`saveEditedSubtitles`)
                    // with no caller, so a fixed cue could never be kept — the
                    // only way to persist one was to press Run again. Enabled on
                    // the edit count, not on `resultReady`: a loaded run with no
                    // edits has nothing to save (UI review 5.13).
                    AppButton {
                        objectName: "review.saveChanges"
                        text: "Save changes"
                        small: true
                        iconName: "save"
                        enabled: appBridge.cueEditedCount > 0
                        onClicked: appBridge.saveEditedSubtitlesToDefault()
                    },
                    AppButton {
                        text: "Revert all"
                        small: true
                        variant: "ghost"
                        iconName: "undo"
                        enabled: appBridge.cueEditedCount > 0
                        onClicked: appBridge.revertAllEdits()
                    }
                ]

                CuePreviewTable {
                    id: table
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    onRowSelected: (row) => root.selectedRow = row
                }
            }

            AppCard {
                Layout.fillWidth: true
                title: "Timeline"
                headerExtra: [
                    Chip {
                        visible: appBridge.qualityErrors > 0
                        text: appBridge.qualityErrors + " errors"
                        tone: "err"
                        mono: true
                    },
                    Chip {
                        visible: appBridge.qualityWarnings > 0
                        text: appBridge.qualityWarnings + " warnings"
                        tone: "warn"
                        mono: true
                    }
                ]

                ColumnLayout {
                    width: parent.width
                    spacing: 8

                    Timeline {
                        id: timeline
                        Layout.fillWidth: true
                        bars: appBridge.cueTimeline
                        ruler: appBridge.cueTimelineRuler
                        selectedCue: root.selectedCueNumber
                        playhead: -1

                        // Click a bar to jump to that cue; drag across the
                        // track to filter the table to that span. The timeline
                        // used to be read-only, so finding the cue behind a red
                        // bar was a manual hunt (UI review 5.3).
                        onBarClicked: (cue) => table.selectCue(cue)
                        onRangeSelected: (first, last) => table.filterToCueRange(first, last)
                    }

                    Label {
                        Layout.fillWidth: true
                        visible: appBridge.cueTimeline.length === 0
                        text: appBridge.resultReady
                              ? "No timed cues in this result."
                              : "Run a translation to see the cue timeline."
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                    }
                }
            }
        }

        // ========================================================== RIGHT ==
        ScrollView {
            Layout.preferredWidth: 412
            Layout.minimumWidth: 340
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: 412 - 10
                spacing: 16

                AppCard {
                    Layout.fillWidth: true
                    title: "Cue inspector"
                    headerExtra: [
                        Chip {
                            text: root.selectedRow >= 0
                                  ? root.selectedCueNumber + " / " + table.count
                                  : "\u2014"
                            mono: true
                        }
                    ]

                    CueInspector {
                        Layout.fillWidth: true
                        row: root.selectedRow
                        cueNumber: root.selectedCueNumber
                        totalCues: table.count
                        onNavigate: (delta) => table.step(delta)
                    }
                }

                AppCard {
                    Layout.fillWidth: true
                    title: "Find & replace"
                    // The scope is stated, not implied: this card has no cue
                    // selection concept, so "every cue" is the honest answer and
                    // it belongs on screen before the button is pressed.
                    note: "every cue \u00b7 " + appBridge.qualityTotalCues + " total"

                    ColumnLayout {
                        width: parent.width
                        spacing: 8

                        CompactTextField {
                            id: findField
                            Layout.fillWidth: true
                            placeholderText: "Find\u2026"
                            label: "Find text"
                        }

                        CompactTextField {
                            id: replaceField
                            Layout.fillWidth: true
                            placeholderText: "Replace with\u2026"
                            label: "Replacement text"
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            AppSwitch {
                                id: regexSwitch
                                text: "Regex"
                                checked: false
                                accessibleName: "Treat the find text as a regular expression"
                            }

                            Item { Layout.fillWidth: true }

                            // Live match count. `findField.text` and
                            // `regexSwitch.checked` are the only inputs, so the
                            // count is recomputed whenever either changes —
                            // there is no second source of truth to drift.
                            Label {
                                id: matchLabel
                                objectName: "review.matchCount"
                                readonly property int matches: {
                                    const needle = findField.text
                                    const asRegex = regexSwitch.checked
                                    appBridge.cueEditedCount   // re-count after a replace
                                    if (needle === "")
                                        return 0
                                    return appBridge.countCueMatches(needle, asRegex)
                                }
                                text: findField.text === ""
                                      ? ""
                                      : matches === 1 ? "1 match"
                                                      : matches + " matches"
                                color: matches === 0 ? Theme.warning : Theme.textMuted
                                font.pixelSize: Theme.fontSmall
                                font.family: Theme.monoFont
                            }

                            AppButton {
                                objectName: "review.replaceAll"
                                text: "Replace all"
                                small: true
                                iconName: "refresh"
                                // Disabled until there is something to replace,
                                // not merely until a needle was typed.
                                enabled: appBridge.resultReady
                                         && matchLabel.matches > 0
                                onClicked: {
                                    const n = appBridge.replaceInCues(
                                                    findField.text, replaceField.text,
                                                    regexSwitch.checked)
                                    root.replaceNotice = n === 1
                                            ? "1 replacement"
                                            : n + " replacements"
                                }
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            visible: root.replaceNotice !== ""
                            text: root.replaceNotice
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSmall
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }

    // Empty = a prompt and nothing else.
    EmptyState {
        objectName: "review.emptyState"
        anchors.centerIn: parent
        width: Math.min(parent.width - 80, 460)
        visible: !appBridge.resultReady
        iconName: "list"
        title: "No cues to review yet"
        body: "Run a translation and the cue table, timeline and inspector "
              + "appear here. Every row is editable in place."
        actionLabel: "Go to Run"
        onActionTriggered: root.navigateRequested(0)
    }
}
