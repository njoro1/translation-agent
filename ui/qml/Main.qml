import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "."
import "components"
import "pages"

// Application shell: 56px command bar, 64px icon rail, the workspace stack, and
// a 30px status bar. Every page is instantiated once and kept alive, so
// switching screens never loses state.
ApplicationWindow {
    id: window

    readonly property bool isYouTubeMode: appBridge.pipelineMode === "youtube_cloud"
    readonly property bool isLocalMode: appBridge.pipelineMode !== "youtube_cloud"
    readonly property bool isOfflineMode: appBridge.pipelineMode === "offline"

    property int currentPage: 0

    x: appBridge.windowX
    y: appBridge.windowY
    width: appBridge.windowWidth
    height: appBridge.windowHeight
    minimumWidth: 1180
    minimumHeight: 720
    visible: true
    title: "Translation Agent"
    color: Theme.background

    // Theme is a QML singleton and must not depend on the `appBridge` context
    // property, so the persisted appearance is pushed into it from here.
    Binding { target: Theme; property: "themeName"; value: appBridge.themeName }
    Binding { target: Theme; property: "comfortable"; value: appBridge.comfortable }
    Binding { target: Theme; property: "reducedMotion"; value: appBridge.reducedMotion }
    Binding { target: Theme; property: "accentName"; value: appBridge.accentName }

    function switchToTab(index) {
        if (index >= 0 && index <= 4)
            window.currentPage = index
    }

    // Bridge-initiated navigation (error card -> Log page, "Advanced" -> Settings).
    Connections {
        target: appBridge

        function onRequestTab(index) {
            window.switchToTab(index)
        }

        function onRequestAdvanced() {
            window.switchToTab(4)
        }

        function onFocusCueIndexChanged() {
            if (appBridge.focusCueIndex >= 0)
                window.switchToTab(1)
        }
    }

    // --- Global keyboard shortcuts ---------------------------------------
    Shortcut { sequence: "Ctrl+1"; context: Qt.ApplicationShortcut; onActivated: window.switchToTab(0) }
    Shortcut { sequence: "Ctrl+2"; context: Qt.ApplicationShortcut; onActivated: window.switchToTab(1) }
    Shortcut { sequence: "Ctrl+3"; context: Qt.ApplicationShortcut; onActivated: window.switchToTab(2) }
    Shortcut { sequence: "Ctrl+4"; context: Qt.ApplicationShortcut; onActivated: window.switchToTab(3) }
    Shortcut { sequence: "Ctrl+L"; context: Qt.ApplicationShortcut; onActivated: window.switchToTab(3) }
    Shortcut { sequence: "Ctrl+,"; context: Qt.ApplicationShortcut; onActivated: window.switchToTab(4) }
    Shortcut {
        sequence: "Ctrl+K"
        context: Qt.ApplicationShortcut
        onActivated: palette.toggle()
    }
    Shortcut {
        sequence: "Ctrl+Return"
        context: Qt.ApplicationShortcut
        onActivated: if (!appBridge.isRunning) appBridge.runTranslation()
    }
    Shortcut {
        sequence: "Ctrl+Enter"
        context: Qt.ApplicationShortcut
        onActivated: if (!appBridge.isRunning) appBridge.runTranslation()
    }
    Shortcut {
        sequence: "Ctrl+."
        context: Qt.ApplicationShortcut
        onActivated: if (appBridge.isRunning) appBridge.cancelRun()
    }
    Shortcut {
        sequence: "Ctrl+S"
        context: Qt.ApplicationShortcut
        onActivated: appBridge.saveEditedSubtitlesToDefault()
    }
    Shortcut {
        sequence: "Ctrl+F"
        context: Qt.ApplicationShortcut
        onActivated: {
            window.switchToTab(1)
            reviewPage.focusSearch()
        }
    }
    Shortcut {
        sequence: "Ctrl+R"
        context: Qt.ApplicationShortcut
        onActivated: if (!appBridge.isRunning) appBridge.runTranslation()
    }

    onClosing: {
        appBridge.saveWindowState(
            Math.round(x) + "," + Math.round(y) + ","
            + Math.round(width) + "," + Math.round(height)
        )
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ===================================================== COMMAND BAR ==
        CommandBar {
            id: commandBar
            Layout.fillWidth: true
            page: window.currentPage
            fileName: appBridge.outputPathResolved !== ""
                      ? appBridge.outputPathResolved.split(/[\\/]/).pop()
                      : (appBridge.filePath !== "" ? appBridge.filePath.split(/[\\/]/).pop() : "")
            cueCount: appBridge.qualityTotalCues
            issueCount: appBridge.qualityErrors + appBridge.qualityWarnings

            onOpenPalette: palette.toggle()
            onExportReportRequested: appBridge.exportQualityReport()
            onExportLogRequested: appBridge.exportLog()
            onSaveSubtitlesRequested: appBridge.saveEditedSubtitlesToDefault()
            onRecheckRequested: appBridge.recheckQuality()
            onSaveSettingsRequested: appBridge.saveSettings()
        }

        // ========================================================= WORKSPACE =
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            IconRail {
                Layout.fillHeight: true
                currentIndex: window.currentPage
                reviewBadge: appBridge.qualityErrors + appBridge.qualityWarnings
                showBadge: appBridge.resultReady
                           && (appBridge.qualityErrors + appBridge.qualityWarnings) > 0
                onNavigate: (index) => window.switchToTab(index)
                onOpenPalette: palette.toggle()
            }

            StackLayout {
                id: stack
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: window.currentPage

                RunPage {
                    id: runPage
                    onNavigateRequested: (page) => window.switchToTab(page)
                    onOpenSettingsRequested: (section) => {
                        window.switchToTab(4)
                        settingsPage.currentSection = section
                    }
                }

                ReviewPage {
                    id: reviewPage
                    onNavigateRequested: (page) => window.switchToTab(page)
                }

                QualityPage {
                    id: qualityPage
                    onNavigateRequested: (page) => window.switchToTab(page)
                }

                LogPage {
                    id: logPage
                    filterQuery: commandBar.logQuery
                    onNavigateRequested: (page) => window.switchToTab(page)
                }

                SettingsPage {
                    id: settingsPage
                    searchQuery: commandBar.settingsQuery
                    onNavigateRequested: (page) => window.switchToTab(page)
                }
            }
        }

        // ======================================================== STATUS BAR =
        StatusBar {
            Layout.fillWidth: true
            currentIndex: window.currentPage
            onOpenLog: window.switchToTab(3)
        }
    }

    // ==================================================== COMMAND PALETTE ==
    CommandPalette {
        id: palette
        anchors.fill: parent
        onNavigateRequested: (page) => window.switchToTab(page)
        onExportReportRequested: appBridge.exportQualityReport()
        onExportLogRequested: appBridge.exportLog()
    }
}
