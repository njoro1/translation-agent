import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."
import "../components"

// Settings screen — rebuilt around true category gating (UI review 5.1, 5.2).
//
// THE DEFECT THIS FIXES
//
// The left rail listed eight categories, but the content pane was one
// undifferentiated scroll holding all of it, and the highlighted pill had zero
// causal relationship to what was rendered — the same "Translation" pill sat
// over genuine translation fields AND over shortcuts/version/network/about
// across screenshots, with no scroll position where it was correct. The
// free-text "Search settings…" box was the confession that the taxonomy did not
// work, and it was load-bearing because navigation was not.
//
// The fix: clicking a category renders ONLY that category's controls
// (option (a) in the spec — true gating, preferred given the volume). The
// search box still exists but is now a convenience that filters *within* the
// selected category. The `Environment` category is deleted: it owned nothing
// unique, and its raw paths moved behind `Copy diagnostics`.
//
// Every control here writes straight to the bridge, which autosaves. There is
// no Save button and no "Saved" pill — one truth for the save lifecycle
// (UI review 3.4).
Item {
    id: root

    objectName: "settings.page"

    property string currentSection: "appearance"

    signal navigateRequested(int page)

    // Seven categories. Each owns a disjoint set of controls; the assertion
    // that the highlighted category matches the rendered content is a test, not
    // an eyeball check (tests/test_ui_settings_ia.py).
    readonly property var sections: [
        { id: "appearance", label: "Appearance", icon: "sun" },
        { id: "translation", label: "Translation", icon: "globe" },
        { id: "transcription", label: "Transcription", icon: "wave" },
        { id: "models", label: "Models & storage", icon: "layers" },
        { id: "shortcuts", label: "Shortcuts", icon: "keyboard" },
        { id: "privacy", label: "Data & privacy", icon: "shield" },
        { id: "about", label: "About", icon: "info" }
    ]

    readonly property var accentChoices: Theme.accentChoices

    // In-category search. Convenience, never the only way to find something.
    property string searchQuery: ""

    function _match(keywords) {
        const q = root.searchQuery.trim().toLowerCase()
        return q === "" || keywords.toLowerCase().indexOf(q) >= 0
    }

    // --- Palette jumps ---------------------------------------------------
    //
    // The palette knows the *setting* ("api key"), not the layout. It sends a
    // section plus an objectName and this page resolves the two, so the palette
    // never has to learn where a control lives.
    //
    // Two traps, both of which made the jump silently do nothing:
    //   * the in-category filter can hide the target row, so it is cleared;
    //   * `forceActiveFocus()` on a control whose card is still `visible: false`
    //     is a no-op, so the focus is deferred by one event-loop turn.
    property string _pendingFocus: ""
    property string _pendingDialog: ""

    function jumpTo(section, target, dialog) {
        if (section !== "")
            root.currentSection = section
        if (root.searchQuery !== "") {
            root.searchQuery = ""
            searchField.text = ""
        }
        root._pendingFocus = target || ""
        root._pendingDialog = dialog || ""
        jumpTimer.restart()
    }

    function _findByName(node, name) {
        if (!node || !node.children)
            return null
        for (let i = 0; i < node.children.length; i++) {
            const child = node.children[i]
            if (!child)
                continue
            if (child.objectName === name)
                return child
            const hit = root._findByName(child, name)
            if (hit)
                return hit
        }
        return null
    }

    function _applyJump() {
        const dialog = root._pendingDialog
        root._pendingDialog = ""
        if (dialog === "glossary") {
            glossaryDialog.open()
            return
        }
        if (dialog === "purge") {
            purgeDialog.open()
            return
        }
        const target = root._pendingFocus
        root._pendingFocus = ""
        if (target === "")
            return
        const control = root._findByName(root, target)
        if (control && control.forceActiveFocus !== undefined)
            control.forceActiveFocus()
    }

    Timer {
        id: jumpTimer
        interval: 0
        repeat: false
        onTriggered: root._applyJump()
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16

        // ===================================================== SECTION NAV ==
        ColumnLayout {
            Layout.preferredWidth: 212
            Layout.minimumWidth: 180
            Layout.maximumWidth: 212
            Layout.fillHeight: true
            spacing: 4

            Label {
                text: "SETTINGS"
                color: Theme.textMuted
                font.pixelSize: 10
                font.bold: true
                font.letterSpacing: 0.9
                Layout.leftMargin: 10
                Layout.bottomMargin: 4
            }

            Repeater {
                model: root.sections

                delegate: Rectangle {
                    id: navItem
                    required property var modelData

                    readonly property bool isOn: root.currentSection === modelData.id

                    Layout.fillWidth: true
                    implicitHeight: 32
                    radius: Theme.radiusSm
                    color: navItem.isOn ? Theme.accentSoft
                                        : (navHover.hovered ? Theme.surfaceAlt : "transparent")

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 9

                        Icon {
                            name: navItem.modelData.icon
                            width: 15
                            height: 15
                            color: navItem.isOn ? Theme.accent : Theme.textMuted
                        }

                        Label {
                            id: navLabel
                            Layout.fillWidth: true
                            text: navItem.modelData.label
                            color: navItem.isOn ? Theme.accent : Theme.textDim
                            font.pixelSize: Theme.fontSmall
                            font.bold: navItem.isOn
                            elide: Text.ElideRight

                            // The rail is narrow by design, so a long category
                            // name elides as a last resort — but the full name
                            // stays reachable on hover (UI review D4).
                            ToolTip.text: navItem.modelData.label
                            ToolTip.visible: navHover.hovered && navLabel.truncated
                            ToolTip.delay: 500
                        }
                    }

                    HoverHandler { id: navHover }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.currentSection = navItem.modelData.id
                    }

                    Accessible.role: Accessible.PageTab
                    Accessible.name: navItem.modelData.label
                    Accessible.selected: navItem.isOn
                }
            }

            Item { Layout.fillHeight: true }
        }

        // ===================================================== MAIN COLUMN ==
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            // Search lives here now, not in the global command bar: it is a
            // screen-local convenience, and the palette owns cross-category
            // jumps (UI review 5.2, 3.1).
            CompactTextField {
                id: searchField
                objectName: "settings.search"
                Layout.fillWidth: true
                Layout.maximumWidth: 380
                Layout.alignment: Qt.AlignRight
                height: 30
                placeholderText: "Filter this category\u2026"
                label: "Filter settings in the current category"
                onTextEdited: root.searchQuery = text
            }

            Flickable {
                id: flick
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: width
                contentHeight: content.implicitHeight + 36
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                ColumnLayout {
                    id: content
                    x: 0
                    y: 18
                    width: flick.width - 4
                    spacing: 16

                    // ======================================== APPEARANCE ====
                    AppCard {
                        id: appearanceCard
                        objectName: "settings.card.appearance"
                        Layout.fillWidth: true
                        // Gated, not filtered: exactly one card is ever visible.
                        visible: root.currentSection === "appearance"

                        SettingsRow {
                            label: "Theme"
                            visible: root._match("theme dark light appearance")
                            SegmentedControl {
                                objectName: "bound.settings.theme"
                                options: [{ id: "dark", label: "Dark" }, { id: "light", label: "Light" }]
                                current: appBridge.themeName
                                onActivated: (id) => appBridge.themeName = id
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Density"
                            visible: root._match("density compact comfortable spacing appearance")
                            SegmentedControl {
                                objectName: "bound.settings.density"
                                options: [{ id: "compact", label: "Compact" }, { id: "comfortable", label: "Comfortable" }]
                                current: appBridge.comfortable ? "comfortable" : "compact"
                                onActivated: (id) => appBridge.comfortable = (id === "comfortable")
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Reduce motion"
                            visible: root._match("motion animation reduce appearance accessibility")
                            AppSwitch {
                                text: appBridge.reducedMotion ? "Enabled" : "Disabled"
                                checked: appBridge.reducedMotion
                                onToggled: appBridge.reducedMotion = checked
                                accessibleName: "Reduce motion"
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Accent"
                            hint: "Recolours focus rings, active states and the primary action."
                            visible: root._match("accent colour color appearance theme iris azure mint amber rose")

                            RowLayout {
                                spacing: 8

                                Repeater {
                                    model: root.accentChoices

                                    delegate: Rectangle {
                                        id: swatch
                                        required property var modelData

                                        readonly property bool isOn: appBridge.accentName === modelData.id

                                        implicitWidth: 22
                                        implicitHeight: 22
                                        radius: 6
                                        color: Theme.isDark ? modelData.dark : modelData.light
                                        border.width: swatch.isOn ? 2 : 0
                                        border.color: Theme.text

                                        HoverHandler { id: swatchHover }

                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: appBridge.accentName = swatch.modelData.id
                                        }

                                        ToolTip.visible: swatchHover.hovered
                                        ToolTip.delay: 300
                                        ToolTip.text: swatch.modelData.label

                                        Accessible.role: Accessible.RadioButton
                                        Accessible.name: swatch.modelData.label + " accent"
                                        Accessible.checked: swatch.isOn
                                    }
                                }
                            }

                            Item { Layout.fillWidth: true }
                        }
                    }

                    // ======================================= TRANSLATION ====
                    AppCard {
                        id: translationCard
                        objectName: "settings.card.translation"
                        Layout.fillWidth: true
                        visible: root.currentSection === "translation"

                        headerExtra: [
                            Chip {
                                text: appBridge.pipelineMode === "offline" ? "Offline active"
                                      : appBridge.pipelineMode === "local_cloud" ? "Local ASR"
                                      : "YouTube Cloud"
                                tone: appBridge.pipelineMode === "offline" ? "acc" : ""
                            }
                        ]

                        // Derived, not edited here. The Run screen owns the
                        // source × engine pair; Settings renders the resulting
                        // pipeline as a read-only mirror (UI review 1.2 / 6.1).
                        SettingsRow {
                            label: "Pipeline"
                            hint: "Derived from the Run screen's source and engine."
                            visible: root._match("pipeline mode source engine youtube local cloud offline")
                            Label {
                                text: appBridge.sourceEngineSummary
                                color: Theme.textDim
                                font.pixelSize: Theme.fontSmall
                            }
                            Item { Layout.fillWidth: true }
                        }

                        // An invariant, not a control. Rendering "English (locked)"
                        // as a read-only input made it read as a bug (UI review 1.3).
                        SettingsRow {
                            label: "Output language"
                            visible: root._match("output language target english")
                            Label {
                                text: "Always English. The product has no other output language."
                                color: Theme.textDim
                                font.pixelSize: Theme.fontSmall
                                wrapMode: Text.WordWrap
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Context mode"
                            visible: root._match("context mode window deep light standard")
                            BoundComboBox {
                                objectName: "bound.settings.contextMode"
                                Layout.preferredWidth: 230
                                label: "Context mode"
                                textRole: "label"
                                valueRole: "id"
                                model: [
                                    { id: "", label: "Preset default" },
                                    { id: "off", label: "Off" },
                                    { id: "light", label: "Light" },
                                    { id: "standard", label: "Standard" },
                                    { id: "deep", label: "Deep" }
                                ]
                                readValue: function() { return appBridge.contextMode }
                                writeValue: function(v) { appBridge.contextMode = v }
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Batch size"
                            visible: root._match("batch size cues window")
                            CompactTextField {
                                objectName: "settings.batch"
                                Layout.preferredWidth: 90
                                text: appBridge.batch
                                label: "Batch size"
                                validator: IntValidator { bottom: 1; top: 64 }
                                onEditingFinished: appBridge.batch = text
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Translation memory"
                            visible: root._match("memory translation cache reuse")
                            BoundComboBox {
                                objectName: "bound.settings.translationMemory"
                                Layout.preferredWidth: 140
                                label: "Translation memory"
                                textRole: "label"
                                valueRole: "id"
                                model: [
                                    { id: "auto", label: "Auto" },
                                    { id: "on", label: "On" },
                                    { id: "off", label: "Off" }
                                ]
                                readValue: function() { return appBridge.translationMemoryMode }
                                writeValue: function(v) { appBridge.translationMemoryMode = v }
                            }
                            Item { Layout.fillWidth: true }
                        }

                        // One control, not a field + a "Choose" button: the pair
                        // was two widgets for one concept (UI review 6.5).
                        SettingsRow {
                            label: "Glossary"
                            visible: root._match("glossary terms names")
                            AppButton {
                                text: appBridge.glossaryPath === ""
                                      ? "Choose glossary\u2026"
                                      : appBridge.glossaryPath.split(/[\\/]/).pop()
                                small: true
                                iconName: "folder"
                                onClicked: glossaryDialog.open()
                                Accessible.name: appBridge.glossaryPath === ""
                                    ? "Choose a glossary file"
                                    : "Change the glossary file (" + appBridge.glossaryPath + ")"
                            }
                            AppButton {
                                visible: appBridge.glossaryPath !== ""
                                text: "Clear"
                                small: true
                                variant: "ghost"
                                iconName: "x"
                                onClicked: appBridge.glossaryPath = ""
                                Accessible.name: "Clear the glossary file"
                            }
                            Item { Layout.fillWidth: true }
                        }

                        // Invariant, not a toggle: a switch that cannot be switched
                        // off is a fake setting (UI review 1.3).
                        SettingsRow {
                            label: "Foreignization"
                            visible: root._match("foreignization proper nouns honorifics")
                            Label {
                                text: "Always on. Proper nouns and honorifics keep their source form."
                                color: Theme.textDim
                                font.pixelSize: Theme.fontSmall
                                wrapMode: Text.WordWrap
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Strict quality gate"
                            visible: root._match("strict quality gate errors fail")
                            AppSwitch {
                                text: appBridge.strictQuality ? "Enabled" : "Disabled"
                                checked: appBridge.strictQuality
                                onToggled: appBridge.strictQuality = checked
                                accessibleName: "Strict quality gate"
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Rolling scene summary"
                            hint: "Cloud only. Carries a running scene summary between windows."
                            visible: root._match("rolling scene summary context cloud")
                            AppSwitch {
                                text: appBridge.contextSummary ? "Enabled" : "Disabled"
                                checked: appBridge.contextSummary
                                onToggled: appBridge.contextSummary = checked
                                accessibleName: "Rolling scene summary"
                            }
                            Item { Layout.fillWidth: true }
                        }

                        Rectangle {
                            Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft
                            visible: root._match("cloud base url model api key credentials")
                        }

                        SettingsRow {
                            label: "Cloud base URL"
                            visible: root._match("cloud base url endpoint credentials")
                            CompactTextField {
                                Layout.fillWidth: true
                                text: appBridge.baseUrl
                                placeholderText: "provider default"
                                label: "Cloud base URL"
                                onEditingFinished: appBridge.baseUrl = text
                            }
                        }

                        // Effective value + provenance, always visible. A placeholder
                        // such as "from .env when blank" vanishes on focus, which makes
                        // "unset" and "intentionally inheriting" look identical
                        // (UI review 1.4).
                        Label {
                            Layout.fillWidth: true
                            Layout.leftMargin: 198
                            visible: root._match("cloud base url endpoint credentials")
                            text: "In effect: " + appBridge.effectiveBaseUrlText
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontTiny
                            wrapMode: Text.WordWrap
                        }

                        SettingsRow {
                            label: "Cloud model"
                            visible: root._match("cloud model name credentials")
                            CompactTextField {
                                Layout.fillWidth: true
                                text: appBridge.model
                                placeholderText: "inherit from .env"
                                label: "Cloud model"
                                onEditingFinished: appBridge.model = text
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.leftMargin: 198
                            visible: root._match("cloud model name credentials")
                            text: "In effect: " + appBridge.effectiveModelText
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontTiny
                            wrapMode: Text.WordWrap
                        }

                        SettingsRow {
                            label: "API key"
                            visible: root._match("api key secret credentials")
                            CompactTextField {
                                objectName: "settings.apiKey"
                                Layout.fillWidth: true
                                text: appBridge.apiKey
                                echoMode: TextInput.Password
                                placeholderText: "inherit from .env"
                                label: "Cloud API key"
                                onEditingFinished: appBridge.apiKey = text
                            }
                        }

                        // The "never persisted" promise belongs on the secret itself,
                        // inline — not as a hover-only tooltip on the model field
                        // (UI review 1.4, 5.7).
                        Label {
                            Layout.fillWidth: true
                            Layout.leftMargin: 198
                            visible: root._match("api key secret credentials persisted")
                            text: "In effect: " + appBridge.effectiveApiKeyText
                                  + "  \u00b7  Never persisted to disk."
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontTiny
                            wrapMode: Text.WordWrap
                        }

                        Rectangle {
                            Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft
                            visible: root._match("local model path threads ram")
                        }

                        SettingsRow {
                            label: "Local model path"
                            visible: root._match("local model path gguf translation offline")
                            CompactTextField {
                                id: localModelField
                                objectName: "settings.localModel"
                                Layout.fillWidth: true
                                text: appBridge.localModel
                                placeholderText: "auto-detected in the models folder"
                                label: "Local translation model path"
                                onEditingFinished: appBridge.localModel = text
                            }
                            AppButton {
                                text: "Browse"
                                small: true
                                iconName: "folder"
                                onClicked: localModelDialog.open()
                                Accessible.name: "Browse for a translation GGUF file"
                            }
                            // Read-only mirror of the Models & storage row — that table
                            // is the single source for this fact. Previously the same
                            // `missing` state was rendered here AND in the table as two
                            // independent widgets (UI review 5.4).
                            StatusMark {
                                status: appBridge.localModelReady ? "ok" : "todo"
                                text: appBridge.localModelReady ? "ready"
                                    : appBridge.localModelCorrupt ? "incomplete" : "missing"
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.leftMargin: 198
                            visible: appBridge.localModelSelectionProblem !== ""
                            text: appBridge.localModelSelectionProblem
                            color: Theme.warning
                            font.pixelSize: Theme.fontSmall
                            wrapMode: Text.WordWrap
                        }

                        SettingsRow {
                            label: "llama.cpp threads"
                            visible: root._match("threads cpu llama local performance")
                            CompactTextField {
                                Layout.preferredWidth: 90
                                text: appBridge.localThreads
                                label: "llama.cpp threads"
                                validator: IntValidator { bottom: 0; top: 256 }
                                onEditingFinished: appBridge.localThreads = text
                            }
                            Label { text: "0 = auto"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Lock model in RAM"
                            visible: root._match("lock ram mlock memory local performance")
                            AppSwitch {
                                text: appBridge.localMlock ? "Enabled" : "Disabled"
                                checked: appBridge.localMlock
                                onToggled: appBridge.localMlock = checked
                                accessibleName: "Lock the local model in RAM"
                            }
                            Item { Layout.fillWidth: true }
                        }
                    }

                    // ===================================== TRANSCRIPTION ====
                    AppCard {
                        id: transcriptionCard
                        objectName: "settings.card.transcription"
                        Layout.fillWidth: true
                        visible: root.currentSection === "transcription"

                        headerExtra: [
                            Pill {
                                tone: appBridge.asrModelReady ? "ok" : "warn"
                                text: appBridge.asrModelReady ? "SenseVoice + VAD installed"
                                    : appBridge.asrModelCorrupt ? "ASR model file incomplete"
                                    : "ASR models missing"
                            }
                        ]

                        SettingsRow {
                            label: "Spoken language"
                            visible: root._match("spoken language asr audio auto detect")
                            BoundField {
                                objectName: "bound.settings.spokenLanguage"
                                Layout.preferredWidth: 200
                                label: "Spoken language"
                                model: ["auto", "ja", "zh", "zh-TW", "ko", "yue", "en"]
                                readValue: function() { return appBridge.asrLanguage }
                                writeValue: function(v) { appBridge.asrLanguage = v }
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "FFmpeg preprocess"
                            visible: root._match("ffmpeg preprocess audio denoise normalise high-pass")
                            BoundComboBox {
                                objectName: "bound.settings.ffmpegPreprocess"
                                Layout.preferredWidth: 230
                                label: "FFmpeg preprocess"
                                textRole: "label"
                                valueRole: "id"
                                model: [
                                    { id: "auto", label: "Auto (preset)" },
                                    { id: "none", label: "None" },
                                    { id: "basic", label: "Basic high-pass" },
                                    { id: "loudnorm", label: "Loudness normalise" },
                                    { id: "denoise", label: "Denoise + normalise" }
                                ]
                                readValue: function() { return appBridge.asrPreprocess }
                                writeValue: function(v) { appBridge.asrPreprocess = v }
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Threads"
                            visible: root._match("threads asr cpu performance")
                            CompactTextField {
                                Layout.preferredWidth: 88
                                text: appBridge.asrThreads
                                label: "ASR threads"
                                validator: IntValidator { bottom: 1; top: 128 }
                                onEditingFinished: appBridge.asrThreads = text
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Max segment"
                            visible: root._match("max segment length ms asr split")
                            CompactTextField {
                                Layout.preferredWidth: 88
                                text: appBridge.asrMaxSegmentMs
                                label: "Maximum ASR segment (ms)"
                                validator: IntValidator { bottom: 500; top: 60000 }
                                onEditingFinished: appBridge.asrMaxSegmentMs = text
                            }
                            Label { text: "ms"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "End silence"
                            visible: root._match("end silence ms asr trim")
                            CompactTextField {
                                Layout.preferredWidth: 88
                                text: appBridge.asrMaxEndSilenceMs
                                label: "Maximum end silence (ms)"
                                validator: IntValidator { bottom: 0; top: 5000 }
                                onEditingFinished: appBridge.asrMaxEndSilenceMs = text
                            }
                            Label { text: "ms"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Min silence"
                            visible: root._match("min silence seconds asr split vad")
                            CompactTextField {
                                Layout.preferredWidth: 88
                                text: appBridge.asrMinSilenceS
                                label: "Minimum silence (s)"
                                onEditingFinished: appBridge.asrMinSilenceS = text
                            }
                            Label { text: "s"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            Item { Layout.fillWidth: true }
                        }

                        // Wraps instead of clipping at the card edge (UI review 2.2):
                        // three fields plus three unit labels do not fit on one line.
                        Flow {
                            Layout.fillWidth: true
                            visible: root._match("cue budget duration characters cjk ms asr")
                            spacing: 8

                            Label {
                                text: "Cue budget"
                                Layout.preferredWidth: 186
                                color: Theme.textDim
                                font.pixelSize: Theme.fontBody
                            }

                            RowLayout {
                                spacing: 6
                                CompactTextField {
                                    Layout.preferredWidth: 88
                                    text: appBridge.asrMaxCueDurationMs
                                    label: "Maximum cue duration (ms)"
                                    validator: IntValidator { bottom: 500; top: 20000 }
                                    onEditingFinished: appBridge.asrMaxCueDurationMs = text
                                }
                                Label { text: "ms"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            }

                            RowLayout {
                                spacing: 6
                                CompactTextField {
                                    Layout.preferredWidth: 88
                                    text: appBridge.asrMaxCueChars
                                    label: "Maximum cue characters"
                                    validator: IntValidator { bottom: 10; top: 400 }
                                    onEditingFinished: appBridge.asrMaxCueChars = text
                                }
                                Label { text: "chars"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            }

                            RowLayout {
                                spacing: 6
                                CompactTextField {
                                    Layout.preferredWidth: 88
                                    text: appBridge.asrMaxCueCharsCjk
                                    label: "Maximum CJK cue characters"
                                    validator: IntValidator { bottom: 5; top: 200 }
                                    onEditingFinished: appBridge.asrMaxCueCharsCjk = text
                                }
                                Label { text: "CJK"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            }
                        }

                        SettingsRow {
                            label: "Speech / noise"
                            visible: root._match("speech noise threshold db audio vad")
                            CompactTextField {
                                Layout.preferredWidth: 88
                                text: appBridge.asrSpeechNoiseThreshold
                                label: "Speech noise threshold"
                                onEditingFinished: appBridge.asrSpeechNoiseThreshold = text
                            }
                            CompactTextField {
                                Layout.preferredWidth: 88
                                text: appBridge.asrNoiseDb
                                label: "Noise floor (dB)"
                                onEditingFinished: appBridge.asrNoiseDb = text
                            }
                            Label { text: "dB"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Drop ASR tags"
                            visible: root._match("drop asr tags annotation")
                            AppSwitch {
                                text: appBridge.asrNoTags ? "Enabled" : "Disabled"
                                checked: appBridge.asrNoTags
                                onToggled: appBridge.asrNoTags = checked
                                accessibleName: "Drop ASR tags"
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "Keep ASR tags"
                            hint: "Keeps the tags in the source text for the translator to see."
                            visible: root._match("keep asr tags annotation")
                            AppSwitch {
                                text: appBridge.asrKeepTags ? "Enabled" : "Disabled"
                                checked: appBridge.asrKeepTags
                                onToggled: appBridge.asrKeepTags = checked
                                accessibleName: "Keep ASR tags"
                            }
                            Item { Layout.fillWidth: true }
                        }

                        SettingsRow {
                            label: "ASR binary"
                            visible: root._match("asr binary exe path")
                            CompactTextField {
                                Layout.fillWidth: true
                                text: appBridge.asrBin
                                placeholderText: "bundled when blank"
                                label: "ASR binary path"
                                onEditingFinished: appBridge.asrBin = text
                            }
                            AppButton {
                                text: "Browse"
                                small: true
                                iconName: "folder"
                                onClicked: asrBinDialog.open()
                                Accessible.name: "Browse for the ASR binary"
                            }
                        }

                        SettingsRow {
                            label: "VAD binary"
                            visible: root._match("vad binary exe path")
                            CompactTextField {
                                Layout.fillWidth: true
                                text: appBridge.asrVadBin
                                placeholderText: "bundled when blank"
                                label: "VAD binary path"
                                onEditingFinished: appBridge.asrVadBin = text
                            }
                            AppButton {
                                text: "Browse"
                                small: true
                                iconName: "folder"
                                onClicked: asrVadBinDialog.open()
                                Accessible.name: "Browse for the VAD binary"
                            }
                        }

                        SettingsRow {
                            label: "ASR model"
                            visible: root._match("asr model sensevoice gguf path")
                            CompactTextField {
                                Layout.fillWidth: true
                                text: appBridge.asrModel
                                placeholderText: "auto-detected in the models folder"
                                label: "ASR model path"
                                onEditingFinished: appBridge.asrModel = text
                            }
                            AppButton {
                                text: "Browse"
                                small: true
                                iconName: "folder"
                                onClicked: asrModelDialog.open()
                                Accessible.name: "Browse for the ASR GGUF file"
                            }
                        }

                        SettingsRow {
                            label: "VAD model"
                            visible: root._match("vad model gguf path")
                            CompactTextField {
                                Layout.fillWidth: true
                                text: appBridge.asrVadModel
                                placeholderText: "auto-detected in the models folder"
                                label: "VAD model path"
                                onEditingFinished: appBridge.asrVadModel = text
                            }
                            AppButton {
                                text: "Browse"
                                small: true
                                iconName: "folder"
                                onClicked: asrVadModelDialog.open()
                                Accessible.name: "Browse for the VAD GGUF file"
                            }
                        }

                        Label {
                            Layout.fillWidth: true
                            Layout.leftMargin: 198
                            visible: appBridge.asrModelSelectionProblem !== ""
                            text: appBridge.asrModelSelectionProblem
                            color: Theme.warning
                            font.pixelSize: Theme.fontSmall
                            wrapMode: Text.WordWrap
                        }
                    }

                    // ============================================ MODELS ====
                    AppCard {
                        id: modelsCard
                        objectName: "settings.card.models"
                        Layout.fillWidth: true
                        visible: root.currentSection === "models"

                        headerExtra: [
                            Chip {
                                text: appBridge.modelsUsedText + " used"
                                mono: true
                            }
                        ]

                        ColumnLayout {
                            objectName: "settings.modelTable"
                            width: parent.width
                            spacing: 8

                            // Header row. Every column has a MINIMUM width, so no
                            // cell can paint over its neighbour (UI review 2.2, 5.4).
                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: 28
                                radius: Theme.radiusSm
                                color: Theme.surfaceAlt

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 10
                                    anchors.rightMargin: 10
                                    spacing: 8

                                    Label { text: "FILE"; Layout.fillWidth: true; Layout.minimumWidth: 160; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                    Label { text: "SIZE"; Layout.preferredWidth: 92; Layout.minimumWidth: 92; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                    Label { text: "PURPOSE"; Layout.preferredWidth: 96; Layout.minimumWidth: 96; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                    Label { text: "STATE"; Layout.preferredWidth: 124; Layout.minimumWidth: 124; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                    Label { text: ""; Layout.preferredWidth: 116; Layout.minimumWidth: 116; color: Theme.textMuted; font.pixelSize: 10 }
                                }
                            }

                            Repeater {
                                model: appBridge.modelsInventory

                                delegate: Rectangle {
                                    id: modelRow
                                    required property var modelData

                                    Layout.fillWidth: true
                                    implicitHeight: rowLayout.implicitHeight + 14
                                    radius: Theme.radiusXs
                                    color: modelHover.hovered ? Theme.surfaceAlt : "transparent"

                                    ColumnLayout {
                                        id: rowLayout
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.leftMargin: 10
                                        anchors.rightMargin: 10
                                        spacing: 2

                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8

                                            Label {
                                                Layout.fillWidth: true
                                                Layout.minimumWidth: 160
                                                text: modelRow.modelData.file
                                                color: Theme.textDim
                                                font.pixelSize: Theme.fontTiny
                                                font.family: Theme.monoFont
                                                elide: Text.ElideMiddle
                                                ToolTip.visible: fileHover.hovered
                                                ToolTip.delay: 500
                                                ToolTip.text: modelRow.modelData.file
                                                HoverHandler { id: fileHover }
                                            }

                                            // SIZE is bytes only. The folder tail used to be
                                            // appended here and painted over PURPOSE.
                                            Label {
                                                Layout.preferredWidth: 92
                                                Layout.minimumWidth: 92
                                                text: modelRow.modelData.size
                                                color: Theme.textMuted
                                                font.pixelSize: Theme.fontTiny
                                                font.family: Theme.monoFont
                                                elide: Text.ElideRight
                                            }

                                            Label {
                                                Layout.preferredWidth: 96
                                                Layout.minimumWidth: 96
                                                text: modelRow.modelData.purpose
                                                color: Theme.textMuted
                                                font.pixelSize: Theme.fontTiny
                                                elide: Text.ElideRight
                                            }

                                            // The STATE column is the §2.1 reference
                                            // implementation: icon + colour + text.
                                            StatusMark {
                                                Layout.preferredWidth: 124
                                                Layout.minimumWidth: 124
                                                small: true
                                                status: modelRow.modelData.tone === "ok" ? "ok"
                                                      : modelRow.modelData.state === "Not created" ? "unchecked"
                                                      : "todo"
                                                text: modelRow.modelData.state
                                            }

                                            AppButton {
                                                Layout.preferredWidth: 116
                                                Layout.minimumWidth: 116
                                                // The verb comes from Python: you do not
                                                // download a cache the app builds.
                                                text: modelRow.modelData.actionLabel
                                                small: true
                                                variant: modelRow.modelData.actionEnabled
                                                         && modelRow.modelData.tone !== "ok" ? "primary" : "ghost"
                                                enabled: modelRow.modelData.actionEnabled && !appBridge.isRunning
                                                onClicked: appBridge.runModelRowAction(modelRow.modelData.action)
                                                ToolTip.visible: actionHover.hovered
                                                    && modelRow.modelData.actionHint !== ""
                                                ToolTip.delay: 400
                                                ToolTip.text: modelRow.modelData.actionHint
                                                HoverHandler { id: actionHover }
                                            }
                                        }

                                        // Where the file lives / why it was rejected, on
                                        // its own line so it cannot collide with a column.
                                        Label {
                                            Layout.fillWidth: true
                                            visible: modelRow.modelData.note !== ""
                                            text: modelRow.modelData.note
                                            color: Theme.textMuted
                                            font.pixelSize: 10
                                            wrapMode: Text.WordWrap
                                        }
                                    }

                                    HoverHandler { id: modelHover }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: 1
                                color: Theme.borderSoft
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                Icon { name: "folder"; width: 15; height: 15; color: Theme.textMuted }

                                Label {
                                    Layout.fillWidth: true
                                    Layout.minimumWidth: 160
                                    text: appBridge.modelsFolder
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.fontTiny
                                    font.family: Theme.monoFont
                                    elide: Text.ElideMiddle
                                    ToolTip.visible: folderHover.hovered
                                    ToolTip.delay: 500
                                    ToolTip.text: appBridge.modelsFolder
                                    HoverHandler { id: folderHover }
                                }

                                AppButton {
                                    text: "Open folder"
                                    small: true
                                    iconName: "external"
                                    onClicked: appBridge.openModelsFolder()
                                }

                                AppButton {
                                    text: "Purge cache"
                                    small: true
                                    iconName: "x"
                                    onClicked: purgeDialog.open()
                                    Accessible.name: "Purge the translation-memory cache"
                                }
                            }

                            Label {
                                Layout.fillWidth: true
                                text: appBridge.modelDownloadStatus !== "" ? appBridge.modelDownloadStatus
                                                                           : appBridge.localModelDownloadStatus
                                visible: text !== ""
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontSmall
                                wrapMode: Text.WordWrap
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                implicitHeight: 1
                                color: Theme.borderSoft
                            }

                            Label {
                                Layout.fillWidth: true
                                text: "WHERE THE APP LOOKS FOR MODELS"
                                color: Theme.textMuted
                                font.pixelSize: 10
                                font.bold: true
                                font.letterSpacing: 0.8
                            }

                            Label {
                                Layout.fillWidth: true
                                text: "Put the .gguf files in any folder below \u2014 the one next to "
                                      + "TranslationAgent.exe works too. The first folder is where "
                                      + "downloads go."
                                color: Theme.textDim
                                font.pixelSize: Theme.fontSmall
                                wrapMode: Text.WordWrap
                            }

                            Repeater {
                                model: appBridge.modelSearchPaths

                                delegate: RowLayout {
                                    required property var modelData

                                    Layout.fillWidth: true
                                    spacing: 8

                                    Icon {
                                        name: "folder"
                                        width: 14
                                        height: 14
                                        color: modelData.exists ? Theme.textMuted : Theme.textDim
                                    }

                                    Label {
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 160
                                        text: modelData.path
                                        color: modelData.exists ? Theme.text : Theme.textDim
                                        font.pixelSize: Theme.fontTiny
                                        font.family: Theme.monoFont
                                        elide: Text.ElideMiddle
                                        ToolTip.visible: pathHover.hovered
                                        ToolTip.delay: 500
                                        ToolTip.text: modelData.path
                                        HoverHandler { id: pathHover }
                                    }

                                    StatusMark {
                                        visible: modelData.primary
                                        status: "ok"
                                        text: "downloads"
                                        small: true
                                    }

                                    StatusMark {
                                        visible: !modelData.exists
                                        status: "unchecked"
                                        text: "not created yet"
                                        small: true
                                    }

                                    StatusMark {
                                        visible: modelData.exists && !modelData.writable
                                        status: "todo"
                                        text: "read-only"
                                        small: true
                                    }
                                }
                            }
                        }
                    }

                    // ========================================= SHORTCUTS ====
                    // A real remap editor, not a read-only list. A read-only list
                    // under "Settings" was decoration, and it was mirrored in the
                    // palette and the bottom bar too (UI review 5.5).
                    AppCard {
                        id: shortcutsCard
                        objectName: "settings.card.shortcuts"
                        Layout.fillWidth: true
                        visible: root.currentSection === "shortcuts"

                        headerExtra: [
                            AppButton {
                                text: "Reset all"
                                small: true
                                variant: "ghost"
                                iconName: "undo"
                                onClicked: appBridge.resetAllShortcuts()
                                Accessible.name: "Reset every shortcut to its default"
                            }
                        ]

                        Label {
                            Layout.fillWidth: true
                            text: "Click Record, then press the combination you want. "
                                  + "Escape cancels, Backspace clears."
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSmall
                            wrapMode: Text.WordWrap
                        }

                        ColumnLayout {
                            width: parent.width
                            spacing: 6

                            Repeater {
                                model: appBridge.shortcutRows

                                delegate: RowLayout {
                                    id: shortcutRow
                                    required property var modelData

                                    Layout.fillWidth: true
                                    spacing: 8

                                    Label {
                                        Layout.preferredWidth: 186
                                        Layout.minimumWidth: 186
                                        text: modelData.label
                                        color: Theme.textDim
                                        font.pixelSize: Theme.fontBody
                                        elide: Text.ElideRight
                                    }

                                    Rectangle {
                                        implicitWidth: keyLabel.implicitWidth + 16
                                        implicitHeight: 22
                                        radius: Theme.radiusXs
                                        color: Theme.inset
                                        border.width: 1
                                        border.color: shortcutRow.modelData.conflict
                                                      ? Theme.error : Theme.border

                                        Label {
                                            id: keyLabel
                                            anchors.centerIn: parent
                                            text: shortcutRow.modelData.sequence
                                            color: shortcutRow.modelData.conflict
                                                   ? Theme.error : Theme.text
                                            font.pixelSize: Theme.fontTiny
                                            font.family: Theme.monoFont
                                        }
                                    }

                                    StatusMark {
                                        visible: shortcutRow.modelData.conflict
                                        status: "error"
                                        text: "also used by another action"
                                        small: true
                                    }

                                    ShortcutRecorder {
                                        label: "Record"
                                        onRecorded: (sequence) => {
                                            const problem = appBridge.setShortcut(
                                                shortcutRow.modelData.action, sequence)
                                            if (problem !== "")
                                                appBridge.setStatusMessage(problem)
                                        }
                                    }

                                    AppButton {
                                        visible: !shortcutRow.modelData.isDefault
                                        text: "Reset"
                                        small: true
                                        variant: "ghost"
                                        iconName: "undo"
                                        onClicked: appBridge.resetShortcut(shortcutRow.modelData.action)
                                        Accessible.name: "Reset " + shortcutRow.modelData.label
                                    }

                                    Item { Layout.fillWidth: true }
                                }
                            }
                        }
                    }

                    // =========================================== PRIVACY ====
                    AppCard {
                        id: privacyCard
                        objectName: "settings.card.privacy"
                        Layout.fillWidth: true
                        visible: root.currentSection === "privacy"

                        ColumnLayout {
                            width: parent.width
                            spacing: 9

                            KeyValue { key: "Network calls in Offline mode"; value: "none" }
                            KeyValue { key: "API key persisted"; value: "never" }
                            KeyValue { key: "Where settings live"; value: "on this machine only" }

                            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                AppButton {
                                    text: "Open debug.log"
                                    small: true
                                    iconName: "file"
                                    onClicked: appBridge.openDebugLog()
                                }

                                Item { Layout.fillWidth: true }
                            }

                            // Spatially separated from the safe action above, styled
                            // destructive, gated behind a typed confirmation.
                            DangerZone {
                                objectName: "settings.dangerZone"
                                Layout.fillWidth: true
                                Layout.topMargin: 8
                                description: "Resets the theme, paths, ASR options and pipeline "
                                             + "mode to their defaults. Subtitle files and "
                                             + "downloaded models are not touched. Restart the "
                                             + "app to see every default restored."
                                actionLabel: "Clear stored settings"
                                onConfirmed: appBridge.clearStoredSettings()
                            }
                        }
                    }

                    // ============================================= ABOUT ====
                    AppCard {
                        id: aboutCard
                        objectName: "settings.card.about"
                        Layout.fillWidth: true
                        visible: root.currentSection === "about"

                        ColumnLayout {
                            width: parent.width
                            spacing: 9

                            KeyValue { key: "Translation Agent"; value: appBridge.appVersion }
                            KeyValue { key: "Interface"; value: "Subtitle Studio"; mono: true }
                            KeyValue { key: "Output language"; value: "English (always)" }

                            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

                            // One-line summary instead of raw install paths, the
                            // registry key and Python/Qt versions. The full strings
                            // are behind Copy diagnostics (UI review 5.6).
                            Label {
                                Layout.fillWidth: true
                                text: appBridge.environmentSummary
                                color: Theme.textDim
                                font.pixelSize: Theme.fontSmall
                                wrapMode: Text.WordWrap
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                AppButton {
                                    text: "Documentation"
                                    small: true
                                    iconName: "info"
                                    onClicked: appBridge.openDocumentation()
                                }

                                AppButton {
                                    text: "Copy diagnostics"
                                    small: true
                                    iconName: "copy"
                                    onClicked: appBridge.copyToDiagnostics()
                                    Accessible.name: "Copy diagnostics, including paths and versions"
                                }

                                Item { Layout.fillWidth: true }
                            }
                        }
                    }

                    Item { Layout.preferredHeight: 1 }
                }
            }
        }
    }

    FileDialog {
        id: glossaryDialog
        nameFilters: ["Text files (*.txt *.csv *.tsv)", "All files (*)"]
        onAccepted: appBridge.glossaryPath = appBridge.localPath(selectedFile)
    }

    Dialog {
        id: purgeDialog
        modal: true
        title: "Purge the translation-memory cache?"
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: appBridge.purgeTranslationMemory()

        Label {
            width: 360
            wrapMode: Text.WordWrap
            text: "Deletes the stored translation-memory database. "
                  + "Already-written subtitle files are not touched."
            color: Theme.text
            font.pixelSize: Theme.fontBody
        }
    }

    // --- Model / binary pickers -------------------------------------------
    // Typing an absolute path is the worst possible way to point the app at a
    // model on a client machine, so every model and binary row has a Browse.
    // A picked path is persisted by the bridge and used on the next launch.
    FileDialog {
        id: localModelDialog
        title: "Select the translation model (GGUF)"
        currentFolder: appBridge.folderUrl(appBridge.modelsFolder)
        currentFile: appBridge.fileUrl(appBridge.localModel)
        nameFilters: ["GGUF models (*.gguf)", "All files (*)"]
        onAccepted: appBridge.localModel = appBridge.localPath(selectedFile)
    }

    FileDialog {
        id: asrModelDialog
        title: "Select the SenseVoice ASR model (GGUF)"
        currentFolder: appBridge.folderUrl(appBridge.modelsFolder)
        currentFile: appBridge.fileUrl(appBridge.asrModel)
        nameFilters: ["GGUF models (*.gguf)", "All files (*)"]
        onAccepted: appBridge.asrModel = appBridge.localPath(selectedFile)
    }

    FileDialog {
        id: asrVadModelDialog
        title: "Select the VAD model (GGUF)"
        currentFolder: appBridge.folderUrl(appBridge.modelsFolder)
        currentFile: appBridge.fileUrl(appBridge.asrVadModel)
        nameFilters: ["GGUF models (*.gguf)", "All files (*)"]
        onAccepted: appBridge.asrVadModel = appBridge.localPath(selectedFile)
    }

    FileDialog {
        id: asrBinDialog
        title: "Select the ASR binary"
        currentFile: appBridge.fileUrl(appBridge.asrBin)
        nameFilters: ["Executables (*.exe)", "All files (*)"]
        onAccepted: appBridge.asrBin = appBridge.localPath(selectedFile)
    }

    FileDialog {
        id: asrVadBinDialog
        title: "Select the VAD binary"
        currentFile: appBridge.fileUrl(appBridge.asrVadBin)
        nameFilters: ["Executables (*.exe)", "All files (*)"]
        onAccepted: appBridge.asrVadBin = appBridge.localPath(selectedFile)
    }
}
