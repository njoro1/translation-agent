import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// The 56px command bar. One primary action per screen; everything else is a
// control or a status read-out.
//
// ``page`` selects the per-screen controls (0 Run · 1 Review · 2 Quality ·
// 3 Log · 4 Settings) so a single bar serves the whole app.
Rectangle {
    id: root

    property int page: 0
    property string fileName: ""
    property int cueCount: 0
    property int issueCount: 0

    readonly property bool isYouTubeMode: appBridge.pipelineMode === "youtube_cloud"

    property alias logQuery: logField.text
    property alias settingsQuery: settingsField.text

    signal openPalette()
    signal exportReportRequested()
    signal exportLogRequested()
    signal saveSubtitlesRequested()
    signal recheckRequested()
    signal saveSettingsRequested()

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

        // --- Brand ---------------------------------------------------------
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

        // --- Page 0: run controls -----------------------------------------
        ModePicker {
            visible: root.page === 0
        }

        Rectangle {
            visible: root.page === 0
            implicitWidth: 1
            implicitHeight: 22
            color: Theme.border
        }

        PresetPicker {
            visible: root.page === 0
            Layout.preferredWidth: 150
        }

        CompactComboBox {
            id: langCombo
            visible: root.page === 0
            Layout.preferredWidth: 116
            editable: true
            label: root.isYouTubeMode ? "Source language" : "Spoken language"
            editText: root.isYouTubeMode ? appBridge.sourceLang : appBridge.asrLanguage
            model: ["auto", "ja", "zh", "zh-TW", "ko", "yue", "en"]
            onAccepted: root.isYouTubeMode
                        ? (appBridge.sourceLang = langCombo.editText.trim())
                        : (appBridge.asrLanguage = langCombo.editText.trim())
            onActivated: root.isYouTubeMode
                         ? (appBridge.sourceLang = langCombo.editText.trim())
                         : (appBridge.asrLanguage = langCombo.editText.trim())
            ToolTip.visible: hovered
            ToolTip.delay: 500
            ToolTip.text: root.isYouTubeMode
                ? "Source language of the subtitles to translate (auto = detect)."
                : "Spoken language the ASR transcribes (auto = detect)."
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
                    }
                    Chip {
                        visible: root.cueCount > 0
                        text: root.cueCount + " cues"
                        mono: true
                    }
                }
            }
        }

        // --- Page 3: log filter --------------------------------------------
        CompactTextField {
            id: logField
            visible: root.page === 3
            Layout.preferredWidth: 300
            height: 30
            placeholderText: "Filter log lines…"
            label: "Filter log lines"
        }

        // --- Page 4: settings search ---------------------------------------
        CompactTextField {
            id: settingsField
            visible: root.page === 4
            Layout.preferredWidth: 290
            height: 30
            placeholderText: "Search settings…"
            label: "Search settings"
        }

        Item { Layout.fillWidth: true }

        // --- Page 0: status -------------------------------------------------
        StatusPill {
            visible: root.page === 0
        }

        Chip {
            visible: root.page === 0 && appBridge.isRunning && appBridge.progressTotal > 0
            text: Math.round(100 * appBridge.progressDone / Math.max(appBridge.progressTotal, 1)) + "%"
            tone: "acc"
            mono: true
        }

        // --- Pages 1/2: issue summary --------------------------------------
        Pill {
            visible: root.page === 1
            tone: {
                if (appBridge.qualityErrors > 0) return "err"
                if (appBridge.qualityWarnings > 0) return "warn"
                return "ok"
            }
            text: root.page === 1
                  ? (appBridge.resultReady
                     ? appBridge.qualityErrors + " errors · " + appBridge.qualityWarnings + " warnings"
                     : "No report yet")
                  : ""
        }

        Pill {
            visible: root.page === 2
            tone: appBridge.resultStrictState === "fail" ? "err"
                  : appBridge.resultStrictState === "pass" ? "ok" : "mute"
            text: appBridge.resultStrictState === "fail" ? "Strict gate would fail"
                  : appBridge.resultStrictState === "pass" ? "Strict gate passed"
                  : "Strict gate off"
        }

        // --- Page 3: log volume --------------------------------------------
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

        // --- Page 4: persistence state -------------------------------------
        Pill {
            visible: root.page === 4
            tone: "ok"
            text: "Saved"
        }

        // --- Always: palette + theme ---------------------------------------
        AppButton {
            text: "Commands"
            small: true
            variant: "ghost"
            iconName: "keyboard"
            onClicked: root.openPalette()
            Accessible.name: "Open the command palette"
        }

        AppButton {
            text: Theme.isDark ? "Light theme" : "Dark theme"
            small: true
            variant: "ghost"
            iconName: Theme.isDark ? "sun" : "moon"
            onClicked: appBridge.toggleTheme()
            Accessible.name: Theme.isDark ? "Switch to the light theme" : "Switch to the dark theme"
        }

        // --- Page 0: the single primary action -----------------------------
        RunButton {
            visible: root.page === 0
        }

        // --- Pages 1/4 ------------------------------------------------------
        AppButton {
            visible: root.page === 1
            text: "Save changes"
            small: false
            iconName: "save"
            enabled: appBridge.cueEditedCount > 0
            onClicked: root.saveSubtitlesRequested()
        }

        AppButton {
            visible: root.page === 1
            text: "Re-check quality"
            variant: "primary"
            iconName: "refresh"
            enabled: appBridge.resultReady
            onClicked: root.recheckRequested()
        }

        AppButton {
            visible: root.page === 2
            text: "Export report"
            variant: "primary"
            iconName: "download"
            enabled: appBridge.resultReady
            onClicked: root.exportReportRequested()
        }

        AppButton {
            visible: root.page === 3
            text: "Export"
            iconName: "download"
            enabled: appBridge.logText !== ""
            onClicked: root.exportLogRequested()
        }

        AppButton {
            visible: root.page === 4
            text: "Save"
            variant: "primary"
            iconName: "save"
            onClicked: root.saveSettingsRequested()
        }
    }
}
