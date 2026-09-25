import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Command palette (Ctrl K). Every entry maps to a real bridge slot, a real
// navigation, or a real store write — no decorative commands.
//
// Four namespaces (UI review §4.2): Navigate, Actions, Toggles, Settings. The
// split matters because the old flat list made three different kinds of thing
// look identical — a toggle showed no state, so "Toggle theme" told the user
// nothing about which theme they were in, and a settings jump looked like a
// command that would change something.
Item {
    id: root

    property bool opened: false
    property int activeIndex: 0

    signal navigateRequested(int page)
    signal exportReportRequested()
    signal exportLogRequested()
    // `(section, target objectName, dialog)` — resolved by SettingsPage.jumpTo.
    signal settingsRequested(string section, string target, string dialog)

    visible: opened
    focus: opened

    function open() {
        opened = true
        activeIndex = 0
        queryField.text = ""
        queryField.forceActiveFocus()
    }

    function close() {
        opened = false
    }

    function toggle() {
        if (opened)
            close()
        else
            open()
    }

    // Live state for the Toggles namespace. This is a binding over the four
    // stores, so the palette cannot show a stale value — the defect being fixed
    // is a toggle that reads "On" while the store says otherwise.
    readonly property var toggleStates: ({
        theme: appBridge.themeName === "light" ? "Light" : "Dark",
        gate: appBridge.strictQuality ? "On" : "Off",
        summary: appBridge.contextSummary ? "On" : "Off",
        motion: appBridge.reducedMotion ? "Reduced" : "Full"
    })

    readonly property var allCommands: [
        // --- Navigate ------------------------------------------------------
        { ns: "Navigate", label: "Run — source & pipeline", hint: "Ctrl 1",
          icon: "play", action: "goto0", keywords: "run source pipeline screen" },
        { ns: "Navigate", label: "Review — translated cues", hint: "Ctrl 2",
          icon: "list", action: "goto1", keywords: "review cues table" },
        { ns: "Navigate", label: "Quality report", hint: "Ctrl 3",
          icon: "shield", action: "goto2", keywords: "quality issues report" },
        { ns: "Navigate", label: "Console & run history", hint: "Ctrl L",
          icon: "terminal", action: "goto3", keywords: "log console history" },
        { ns: "Navigate", label: "Settings", hint: "Ctrl ,",
          icon: "settings", action: "goto4", keywords: "settings preferences" },
        { ns: "Navigate", label: "Settings › Appearance", hint: "",
          icon: "sun", action: "jump", section: "appearance", target: "",
          dialog: "", keywords: "settings appearance theme density motion" },
        { ns: "Navigate", label: "Settings › Translation", hint: "",
          icon: "globe", action: "jump", section: "translation", target: "",
          dialog: "", keywords: "settings translation batch glossary api key model" },
        { ns: "Navigate", label: "Settings › Transcription", hint: "",
          icon: "wave", action: "jump", section: "transcription", target: "",
          dialog: "", keywords: "settings transcription language audio" },
        { ns: "Navigate", label: "Settings › Models & storage", hint: "",
          icon: "layers", action: "jump", section: "models", target: "",
          dialog: "", keywords: "settings models storage cache" },
        { ns: "Navigate", label: "Settings › Shortcuts", hint: "",
          icon: "keyboard", action: "jump", section: "shortcuts", target: "",
          dialog: "", keywords: "settings shortcuts keys" },
        { ns: "Navigate", label: "Settings › Data & privacy", hint: "",
          icon: "shield", action: "jump", section: "privacy", target: "",
          dialog: "", keywords: "settings privacy data diagnostics" },
        { ns: "Navigate", label: "Settings › About", hint: "",
          icon: "info", action: "jump", section: "about", target: "",
          dialog: "", keywords: "settings about version" },

        // --- Actions -------------------------------------------------------
        { ns: "Actions", label: "Start translation run", hint: "Ctrl Enter",
          icon: "play", action: "run", keywords: "run start translate" },
        { ns: "Actions", label: "Cancel current run", hint: "Ctrl .",
          icon: "stop", action: "cancel", keywords: "cancel stop abort" },
        { ns: "Actions", label: "Re-run last settings", hint: "",
          icon: "refresh", action: "rerun", keywords: "rerun repeat again" },
        { ns: "Actions", label: "Inspect YouTube formats", hint: "",
          icon: "search", action: "inspect", keywords: "inspect youtube formats" },
        { ns: "Actions", label: "Save edited subtitles", hint: "Ctrl S",
          icon: "save", action: "save", keywords: "save cues subtitles write" },
        { ns: "Actions", label: "Re-check quality", hint: "",
          icon: "refresh", action: "recheck", keywords: "recheck quality verify" },
        { ns: "Actions", label: "Revert all edits", hint: "",
          icon: "undo", action: "revert", keywords: "revert undo edits" },
        { ns: "Actions", label: "Open the output file", hint: "",
          icon: "external", action: "open-output", keywords: "open output file external" },
        { ns: "Actions", label: "Export quality report (JSON)", hint: "",
          icon: "download", action: "export-report", keywords: "export report json quality" },
        { ns: "Actions", label: "Export the issue list (CSV)", hint: "",
          icon: "download", action: "export-csv", keywords: "export csv issues quality" },
        { ns: "Actions", label: "Export the log", hint: "",
          icon: "download", action: "export-log", keywords: "export log console" },
        { ns: "Actions", label: "Choose glossary file…", hint: "",
          icon: "folder", action: "jump", section: "translation", target: "",
          dialog: "glossary", keywords: "choose glossary file terms" },
        { ns: "Actions", label: "Purge the translation-memory cache…", hint: "",
          icon: "minus", action: "jump", section: "models", target: "",
          dialog: "purge", keywords: "purge cache translation memory clear" },
        { ns: "Actions", label: "Download translation model", hint: "",
          icon: "download", action: "download-local", keywords: "download translation model gguf" },
        { ns: "Actions", label: "Download ASR models", hint: "",
          icon: "download", action: "download-asr", keywords: "download asr whisper model" },
        { ns: "Actions", label: "Open the models folder", hint: "",
          icon: "folder", action: "open-models", keywords: "open models folder gguf" },
        { ns: "Actions", label: "Copy the log", hint: "",
          icon: "copy", action: "copy-log", keywords: "copy log clipboard" },
        { ns: "Actions", label: "Clear the log", hint: "",
          icon: "x", action: "clear-log", keywords: "clear log console" },
        { ns: "Actions", label: "Open debug.log", hint: "",
          icon: "file", action: "open-debug-log", keywords: "open debug log file" },
        { ns: "Actions", label: "Open the documentation", hint: "",
          icon: "info", action: "readme", keywords: "open documentation readme help" },

        // --- Toggles (each shows its live bound state) ---------------------
        { ns: "Toggles", label: "Theme — dark / light", hint: "",
          icon: "sun", action: "toggle-theme", stateKey: "theme",
          keywords: "toggle theme dark light appearance" },
        { ns: "Toggles", label: "Strict quality gate", hint: "",
          icon: "shield", action: "toggle-gate", stateKey: "gate",
          keywords: "toggle strict quality gate errors fail run" },
        { ns: "Toggles", label: "Rolling scene summary", hint: "",
          icon: "info", action: "toggle-summary", stateKey: "summary",
          keywords: "toggle rolling scene summary context cloud experimental" },
        { ns: "Toggles", label: "Reduce motion", hint: "",
          icon: "stop", action: "toggle-motion", stateKey: "motion",
          keywords: "toggle reduce motion animation accessibility" },

        // --- Settings (jump to the exact field) ----------------------------
        { ns: "Settings", label: "API key", hint: "",
          icon: "shield", action: "jump", section: "translation",
          target: "settings.apiKey", dialog: "",
          keywords: "api key secret credentials token cloud" },
        { ns: "Settings", label: "Batch size", hint: "",
          icon: "layers", action: "jump", section: "translation",
          target: "settings.batch", dialog: "",
          keywords: "batch size cues window batching" },
        { ns: "Settings", label: "Local model path", hint: "",
          icon: "file", action: "jump", section: "translation",
          target: "settings.localModel", dialog: "",
          keywords: "model path gguf local translation offline file" },
        { ns: "Settings", label: "Spoken language", hint: "",
          icon: "globe", action: "jump", section: "transcription",
          target: "bound.settings.spokenLanguage", dialog: "",
          keywords: "spoken source language asr" },
        { ns: "Settings", label: "Audio preprocessing", hint: "",
          icon: "wave", action: "jump", section: "transcription",
          target: "bound.settings.ffmpegPreprocess", dialog: "",
          keywords: "audio preprocessing ffmpeg loudnorm denoise" },
        { ns: "Settings", label: "Translation memory", hint: "",
          icon: "layers", action: "jump", section: "translation",
          target: "bound.settings.translationMemory", dialog: "",
          keywords: "translation memory cache reuse tm" }
    ]

    // Fuzzy match over label, namespace and keywords. The keywords matter for
    // this namespace: the plan asks that typing `api key` lands on the field,
    // and the entry's label is "API key" only by coincidence — `model path`
    // has to reach "Local model path" too.
    readonly property var matches: {
        const q = queryField.text.trim().toLowerCase()
        if (q === "")
            return allCommands
        const out = []
        for (let i = 0; i < allCommands.length; i++) {
            const c = allCommands[i]
            const hay = (c.label + " " + c.ns + " " + (c.keywords || "")).toLowerCase()
            if (hay.indexOf(q) >= 0)
                out.push(c)
        }
        return out
    }

    function _run(entry) {
        switch (entry.action) {
        case "run": appBridge.runTranslation(); break
        case "cancel": appBridge.cancelRun(); break
        case "rerun": appBridge.rerunLastRun(); break
        case "inspect": appBridge.fetchYouTubeInfo(); break
        case "goto0": root.navigateRequested(0); break
        case "goto1": root.navigateRequested(1); break
        case "goto2": root.navigateRequested(2); break
        case "goto3": root.navigateRequested(3); break
        case "goto4": root.navigateRequested(4); break
        case "jump":
            root.settingsRequested(entry.section || "", entry.target || "",
                                   entry.dialog || "")
            break
        case "save": appBridge.saveEditedSubtitlesToDefault(); break
        case "recheck": appBridge.recheckQuality(); break
        case "revert": appBridge.revertAllEdits(); break
        case "open-output": appBridge.openOutputFolder(); break
        case "export-report": root.exportReportRequested(); break
        case "export-csv": appBridge.exportIssueCsv(); break
        case "export-log": root.exportLogRequested(); break
        case "download-asr": appBridge.downloadAsrModels(); break
        case "download-local": appBridge.downloadLocalModel(); break
        case "open-models": appBridge.openModelsFolder(); break
        case "copy-log": appBridge.copyLog(); break
        case "clear-log": appBridge.clearLog(); break
        case "open-debug-log": appBridge.openDebugLog(); break
        case "readme": appBridge.openDocumentation(); break
        case "toggle-theme":
            appBridge.themeName = appBridge.themeName === "light" ? "dark" : "light"
            break
        case "toggle-gate": appBridge.strictQuality = !appBridge.strictQuality; break
        case "toggle-summary": appBridge.contextSummary = !appBridge.contextSummary; break
        case "toggle-motion": appBridge.reducedMotion = !appBridge.reducedMotion; break
        }
        root.close()
    }

    function _move(delta) {
        const n = matches.length
        if (n === 0)
            return
        activeIndex = Math.max(0, Math.min(n - 1, activeIndex + delta))
    }

    function _activate() {
        if (matches.length === 0)
            return
        const i = Math.max(0, Math.min(activeIndex, matches.length - 1))
        _run(matches[i])
    }

    // --- Scrim ------------------------------------------------------------
    Rectangle {
        anchors.fill: parent
        color: Theme.isDark ? Qt.rgba(0.016, 0.024, 0.039, 0.62) : Qt.rgba(0.094, 0.11, 0.157, 0.30)

        MouseArea {
            anchors.fill: parent
            onClicked: root.close()
        }
    }

    Rectangle {
        id: palette
        width: 620
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 96
        implicitHeight: Math.min(560, head.implicitHeight + list.implicitHeight + foot.implicitHeight)
        radius: Theme.radiusXl
        color: Theme.surface
        border.color: Theme.borderStrong
        border.width: 1
        clip: true

        ColumnLayout {
            id: paletteColumn
            anchors.fill: parent
            spacing: 0

            RowLayout {
                id: head
                Layout.fillWidth: true
                Layout.margins: 14
                spacing: 10

                Icon { name: "search"; width: 18; height: 18; color: Theme.textMuted }

                TextField {
                    id: queryField
                    Layout.fillWidth: true
                    placeholderText: "Type a command…"
                    color: Theme.text
                    font.pixelSize: Theme.fontLabel
                    background: Item {}
                    onTextChanged: root.activeIndex = 0
                    Keys.onEscapePressed: root.close()
                    Keys.onUpPressed: root._move(-1)
                    Keys.onDownPressed: root._move(1)
                    Keys.onReturnPressed: root._activate()
                    Keys.onEnterPressed: root._activate()
                }

                Chip {
                    text: "Esc"
                    mono: true
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 1
                color: Theme.borderSoft
            }

            ListView {
                id: list
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(contentHeight, 420)
                Layout.margins: 6
                clip: true
                model: root.matches
                currentIndex: root.activeIndex
                interactive: true
                boundsBehavior: Flickable.StopAtBounds
                spacing: 1

                delegate: Rectangle {
                    id: item
                    required property var modelData
                    required property int index

                    width: list.width
                    height: 34
                    radius: Theme.radiusSm
                    color: index === root.activeIndex ? Theme.accentSoft : "transparent"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 11

                        Icon {
                            name: item.modelData.icon
                            width: 16
                            height: 16
                            color: index === root.activeIndex ? Theme.accent : Theme.textMuted
                        }

                        Label {
                            Layout.fillWidth: true
                            text: item.modelData.ns + " · " + item.modelData.label
                            color: index === root.activeIndex ? Theme.text : Theme.textDim
                            font.pixelSize: Theme.fontBody
                            elide: Text.ElideRight
                        }

                        // A toggle must state the value it is *in*, not just the
                        // thing it flips: "Toggle theme" told the user nothing
                        // about which theme they had (UI review 4.2).
                        Chip {
                            visible: item.modelData.stateKey !== undefined
                            text: item.modelData.stateKey !== undefined
                                  ? root.toggleStates[item.modelData.stateKey] : ""
                            mono: true
                            tone: index === root.activeIndex ? "acc" : ""
                        }

                        Chip {
                            visible: item.modelData.hint !== ""
                            text: item.modelData.hint
                            mono: true
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.activeIndex = index
                            root._run(item.modelData)
                        }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    visible: list.count === 0
                    text: "No matching command."
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontBody
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 1
                color: Theme.borderSoft
            }

            RowLayout {
                id: foot
                Layout.fillWidth: true
                Layout.margins: 10
                spacing: 8

                Chip { text: "↑ ↓"; mono: true }
                Chip { text: "Enter"; mono: true }
                Item { Layout.fillWidth: true }
                Label {
                    text: root.matches.length + " of " + root.allCommands.length
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontTiny
                }
            }
        }
    }

    Shortcut {
        sequence: "Escape"
        enabled: root.opened
        context: Qt.WindowShortcut
        onActivated: root.close()
    }
}
