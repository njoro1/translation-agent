import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Command palette (Ctrl K). Every entry maps to a real bridge slot or a real
// navigation — no decorative commands.
Item {
    id: root

    property bool opened: false
    property int activeIndex: 0

    signal navigateRequested(int page)
    signal exportReportRequested()
    signal exportLogRequested()

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

    readonly property var allCommands: [
        { group: "Run", label: "Start translation run", hint: "Ctrl Enter", icon: "play", action: "run" },
        { group: "Run", label: "Cancel current run", hint: "Ctrl .", icon: "stop", action: "cancel" },
        { group: "Run", label: "Re-run last settings", hint: "", icon: "refresh", action: "rerun" },
        { group: "Run", label: "Inspect YouTube formats", hint: "", icon: "search", action: "inspect" },
        { group: "Go to", label: "Run — source & pipeline", hint: "Ctrl 1", icon: "play", action: "goto0" },
        { group: "Go to", label: "Review — translated cues", hint: "Ctrl 2", icon: "list", action: "goto1" },
        { group: "Go to", label: "Quality report", hint: "Ctrl 3", icon: "shield", action: "goto2" },
        { group: "Go to", label: "Console & run history", hint: "Ctrl L", icon: "terminal", action: "goto3" },
        { group: "Go to", label: "Settings", hint: "Ctrl ,", icon: "settings", action: "goto4" },
        { group: "Cues", label: "Save edited subtitles", hint: "Ctrl S", icon: "save", action: "save" },
        { group: "Cues", label: "Re-check quality", hint: "", icon: "refresh", action: "recheck" },
        { group: "Cues", label: "Revert all edits", hint: "", icon: "undo", action: "revert" },
        { group: "Cues", label: "Open the output file", hint: "", icon: "external", action: "open-output" },
        { group: "Export", label: "Export quality report (JSON)", hint: "", icon: "download", action: "export-report" },
        { group: "Export", label: "Export the log", hint: "", icon: "download", action: "export-log" },
        { group: "Models", label: "Download ASR models", hint: "", icon: "download", action: "download-asr" },
        { group: "Models", label: "Download translation model", hint: "", icon: "download", action: "download-local" },
        { group: "Models", label: "Open the models folder", hint: "", icon: "folder", action: "open-models" },
        { group: "Log", label: "Copy the log", hint: "", icon: "copy", action: "copy-log" },
        { group: "Log", label: "Clear the log", hint: "", icon: "x", action: "clear-log" },
        { group: "Log", label: "Open debug.log", hint: "", icon: "file", action: "open-debug-log" },
        { group: "App", label: "Toggle light / dark theme", hint: "", icon: "sun", action: "theme" },
        { group: "App", label: "Open the documentation", hint: "", icon: "info", action: "readme" }
    ]

    readonly property var matches: {
        var q = queryField.text.trim().toLowerCase()
        if (q === "")
            return allCommands
        var out = []
        for (var i = 0; i < allCommands.length; i++) {
            if (allCommands[i].label.toLowerCase().indexOf(q) >= 0
                    || allCommands[i].group.toLowerCase().indexOf(q) >= 0)
                out.push(allCommands[i])
        }
        return out
    }

    function _run(action) {
        switch (action) {
        case "run": appBridge.runTranslation(); break
        case "cancel": appBridge.cancelRun(); break
        case "rerun": appBridge.rerunLastRun(); break
        case "inspect": appBridge.fetchYouTubeInfo(); break
        case "goto0": root.navigateRequested(0); break
        case "goto1": root.navigateRequested(1); break
        case "goto2": root.navigateRequested(2); break
        case "goto3": root.navigateRequested(3); break
        case "goto4": root.navigateRequested(4); break
        case "save": appBridge.saveEditedSubtitlesToDefault(); break
        case "recheck": appBridge.recheckQuality(); break
        case "revert": appBridge.revertAllEdits(); break
        case "open-output": appBridge.openOutputFolder(); break
        case "export-report": root.exportReportRequested(); break
        case "export-log": root.exportLogRequested(); break
        case "download-asr": appBridge.downloadAsrModels(); break
        case "download-local": appBridge.downloadLocalModel(); break
        case "open-models": appBridge.openModelsFolder(); break
        case "copy-log": appBridge.copyLog(); break
        case "clear-log": appBridge.clearLog(); break
        case "open-debug-log": appBridge.openDebugLog(); break
        case "theme": appBridge.toggleTheme(); break
        case "readme": appBridge.openDocumentation(); break
        }
        root.close()
    }

    function _move(delta) {
        var n = matches.length
        if (n === 0)
            return
        activeIndex = Math.max(0, Math.min(n - 1, activeIndex + delta))
    }

    function _activate() {
        if (matches.length === 0)
            return
        var i = Math.max(0, Math.min(activeIndex, matches.length - 1))
        _run(matches[i].action)
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
                            text: item.modelData.group + " · " + item.modelData.label
                            color: index === root.activeIndex ? Theme.text : Theme.textDim
                            font.pixelSize: Theme.fontBody
                            elide: Text.ElideRight
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
                            root._run(item.modelData.action)
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
