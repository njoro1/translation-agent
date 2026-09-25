import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// The 56px command bar (UI review 3.1).
//
// It used to carry eight concerns, two of which duplicated Settings/Run
// (the mode segmented control and two unlabeled language dropdowns), one of
// which was mis-semantyped (an action-label "Light theme" button), and whose
// primary action mutated colour + label and truncated at the window edge.
//
// Final composition, left to right:
//   1. Identity (logo + product name)
//   2. One read-only global status strip
//   3. spacer
//   4. Theme toggle — a real state-showing control bound to `ui.theme`
//   5. Commands button (opens the palette)
//   6. The one primary action for the current screen
//
// Deliberately NOT here any more: the mode segmented control, the preset
// picker, the language dropdowns, the Settings search field, and the
// persistent Save button.
Rectangle {
    id: root

    objectName: "chrome.bar"

    property int page: 0
    property string fileName: ""
    property int cueCount: 0
    property int issueCount: 0

    property alias logQuery: logField.text

    signal openPalette()
    signal exportReportRequested()
    signal exportLogRequested()
    signal saveSubtitlesRequested()
    signal recheckRequested()

    implicitHeight: Theme.topbarHeight
    color: Theme.surface

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.borderSoft
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 14
        spacing: 14

        // --- 1. Identity ---------------------------------------------------
        RowLayout {
            spacing: 10

            Rectangle {
                implicitWidth: 30
                implicitHeight: 30
                radius: 9
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.lighter(Theme.accent, 1.25) }
                    GradientStop { position: 1.0; color: Theme.accent }
                }

                Label {
                    anchors.centerIn: parent
                    text: "T"
                    color: "#FFFFFF"
                    font.pixelSize: Theme.fontTitle
                    font.bold: true
                }
            }

            ColumnLayout {
                spacing: 0

                Label {
                    text: "Translation Agent"
                    color: Theme.text
                    font.pixelSize: Theme.fontBody
                    font.bold: true
                }
                Label {
                    text: "SUBTITLE STUDIO"
                    color: Theme.textMuted
                    font.pixelSize: 10
                    font.letterSpacing: 1.0
                }
            }
        }

        Rectangle {
            implicitWidth: 1
            implicitHeight: 22
            color: Theme.border
        }

        // --- 2. One read-only status mirror --------------------------------
        StatusStrip {
            id: statusStrip
            objectName: "chrome.statusStrip"
        }

        // --- Pages 1/2: the loaded result ----------------------------------
        RowLayout {
            visible: root.page === 1 || root.page === 2
            spacing: 8

            Rectangle {
                implicitHeight: 30
                implicitWidth: fileRow.implicitWidth + 20
                radius: Theme.radiusSm
                color: Theme.surfaceAlt
                border.color: Theme.border
                border.width: 1

                RowLayout {
                    id: fileRow
                    anchors.centerIn: parent
                    spacing: 8

                    Icon { name: "file"; width: 15; height: 15; color: Theme.textMuted }
                    Label {
                        text: root.fileName !== "" ? root.fileName : "No result loaded"
                        color: Theme.textDim
                        font.pixelSize: Theme.fontSmall
                        elide: Text.ElideMiddle
                        Layout.maximumWidth: 260
                        ToolTip.visible: fileNameHover.hovered && root.fileName !== ""
                        ToolTip.delay: 500
                        ToolTip.text: root.fileName
                        HoverHandler { id: fileNameHover }
                    }
                    Chip {
                        visible: root.cueCount > 0
                        text: root.cueCount + " cues"
                        mono: true
                    }
                }
            }
        }

        // --- Page 3: log filter (genuinely screen-local) --------------------
        CompactTextField {
            id: logField
            visible: root.page === 3
            Layout.preferredWidth: 300
            height: 30
            placeholderText: "Filter log lines\u2026"
            label: "Filter log lines"
        }

        // --- Pages 1/3: read-only volume mirrors ----------------------------
        Pill {
            visible: root.page === 1
            tone: {
                if (appBridge.qualityErrors > 0) return "err"
                if (appBridge.qualityWarnings > 0) return "warn"
                return "ok"
            }
            text: appBridge.resultReady
                  ? appBridge.qualityErrors + " errors \u00b7 " + appBridge.qualityWarnings + " warnings"
                  : "No report yet"
        }

        Pill {
            visible: root.page === 3
            tone: appBridge.logErrorCount > 0 ? "err"
                  : appBridge.logWarnCount > 0 ? "warn" : "mute"
            text: appBridge.logErrorCount > 0
                  ? appBridge.logErrorCount + " errors"
                  : appBridge.logWarnCount > 0
                    ? appBridge.logWarnCount + " warnings"
                    : "No problems logged"
        }

        Item { Layout.fillWidth: true }

        // --- 5. Commands ----------------------------------------------------
        AppButton {
            objectName: "chrome.commands"
            text: "Commands"
            small: true
            variant: "ghost"
            iconName: "keyboard"
            onClicked: root.openPalette()
            Accessible.name: "Open the command palette"
        }

        // --- 4. Theme toggle (state-showing, not an action label) ------------
        SegmentedControl {
            objectName: "bound.chrome.theme"
            options: [
                { id: "dark", label: "Dark" },
                { id: "light", label: "Light" }
            ]
            current: appBridge.themeName
            onActivated: (id) => appBridge.themeName = id
            Accessible.name: "Interface theme"
        }

        // --- 6. The one primary action --------------------------------------
        RunButton {
            objectName: "chrome.primary.run"
            visible: root.page === 0
        }

        AppButton {
            objectName: "chrome.primary.recheck"
            visible: root.page === 1
            text: "Re-check quality"
            variant: "primary"
            iconName: "refresh"
            enabled: appBridge.resultReady
            onClicked: root.recheckRequested()
        }

        AppButton {
            objectName: "chrome.primary.exportReport"
            visible: root.page === 2
            text: "Export report"
            variant: "primary"
            iconName: "download"
            enabled: appBridge.resultReady
            onClicked: root.exportReportRequested()
        }

        AppButton {
            objectName: "chrome.primary.exportLog"
            visible: root.page === 3
            text: "Export"
            iconName: "download"
            enabled: appBridge.logText !== ""
            onClicked: root.exportLogRequested()
        }

        // Page 4 (Settings) intentionally has no primary action: autosave
        // commits on its own and the status strip mirrors the state.
    }
}
