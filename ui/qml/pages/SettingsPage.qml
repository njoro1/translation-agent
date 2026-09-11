import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."
import "../components"

// Settings screen. Section nav on the left, cards on the right. The search box
// in the command bar filters the cards, and every control writes straight to
// the bridge (which persists it), so there is no separate "apply" step beyond
// the bar's Save button re-persisting the form.
Item {
    id: root

    property string searchQuery: ""
    property string currentSection: "appearance"

    signal navigateRequested(int page)

    readonly property var sections: [
        { id: "appearance", label: "Appearance", icon: "sun" },
        { id: "translation", label: "Translation", icon: "globe" },
        { id: "transcription", label: "Transcription", icon: "wave" },
        { id: "models", label: "Models & storage", icon: "layers" },
        { id: "shortcuts", label: "Shortcuts", icon: "keyboard" },
        { id: "environment", label: "Environment", icon: "terminal" },
        { id: "privacy", label: "Data & privacy", icon: "shield" },
        { id: "about", label: "About", icon: "info" }
    ]

    readonly property var accentChoices: Theme.accentChoices

    function _show(keywords) {
        const q = root.searchQuery.trim().toLowerCase()
        return q === "" || keywords.toLowerCase().indexOf(q) >= 0
    }

    function _scrollTo(id) {
        root.currentSection = id
        var card = null
        if (id === "appearance") card = appearanceCard
        else if (id === "translation") card = translationCard
        else if (id === "transcription") card = transcriptionCard
        else if (id === "models") card = modelsCard
        else if (id === "shortcuts") card = shortcutsCard
        else if (id === "environment") card = environmentCard
        else if (id === "privacy") card = privacyCard
        else if (id === "about") card = aboutCard
        if (card === null)
            return
        const p = card.mapToItem(content, 0, 0)
        flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, p.y - 18))
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16

        // ===================================================== SECTION NAV ==
        ColumnLayout {
            Layout.preferredWidth: 212
            Layout.minimumWidth: 180
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
                            Layout.fillWidth: true
                            text: navItem.modelData.label
                            color: navItem.isOn ? Theme.accent : Theme.textDim
                            font.pixelSize: Theme.fontSmall
                            font.bold: navItem.isOn
                            elide: Text.ElideRight
                        }
                    }

                    HoverHandler { id: navHover }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root._scrollTo(navItem.modelData.id)
                    }

                    Accessible.role: Accessible.PageTab
                    Accessible.name: navItem.modelData.label
                    Accessible.selected: navItem.isOn
                }
            }

            Item { Layout.fillHeight: true }
        }

        // ===================================================== MAIN COLUMN ==
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

                // ============================================ APPEARANCE ====
                AppCard {
                    id: appearanceCard
                    Layout.fillWidth: true
                    visible: root._show("appearance theme density motion accent dark light compact comfortable reduce motion interface")

                    SettingsRow {
                        label: "Theme"
                        SegmentedControl {
                            options: [{ id: "dark", label: "Dark" }, { id: "light", label: "Light" }]
                            current: appBridge.themeName
                            onActivated: (id) => appBridge.themeName = id
                        }
                        Item { Layout.fillWidth: true }
                    }

                    SettingsRow {
                        label: "Density"
                        SegmentedControl {
                            options: [{ id: "compact", label: "Compact" }, { id: "comfortable", label: "Comfortable" }]
                            current: appBridge.comfortable ? "comfortable" : "compact"
                            onActivated: (id) => appBridge.comfortable = (id === "comfortable")
                        }
                        Item { Layout.fillWidth: true }
                    }

                    SettingsRow {
                        label: "Reduce motion"
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
                        hint: "Recolours the whole interface."

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

                // =========================================== TRANSLATION ====
                AppCard {
                    id: translationCard
                    Layout.fillWidth: true
                    visible: root._show("translation backend model context batch memory glossary strict quality gate rolling summary api key base url prompt language cloud local")

                    headerExtra: [
                        Chip {
                            text: appBridge.pipelineMode === "offline" ? "Offline active"
                                  : appBridge.pipelineMode === "local_asr_cloud_translate" ? "Local ASR"
                                  : "YouTube Cloud"
                            tone: appBridge.pipelineMode === "offline" ? "acc" : ""
                        }
                    ]

                    SettingsRow {
                        label: "Pipeline"
                        ModePicker {}
                        Item { Layout.fillWidth: true }
                    }

                    SettingsRow {
                        label: "Target language"
                        CompactTextField {
                            Layout.preferredWidth: 180
                            readOnly: true
                            text: "English (locked)"
                            label: "Target language"
                        }
                        Item { Layout.fillWidth: true }
                    }

                    SettingsRow {
                        label: "Context mode"
                        CompactComboBox {
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
                            currentIndex: {
                                for (let i = 0; i < model.length; i++)
                                    if (model[i].id === appBridge.contextMode) return i
                                return 0
                            }
                            onActivated: appBridge.contextMode = currentValue
                        }
                        Item { Layout.fillWidth: true }
                    }

                    SettingsRow {
                        label: "Batch size"
                        CompactTextField {
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
                        CompactComboBox {
                            Layout.preferredWidth: 140
                            label: "Translation memory"
                            textRole: "label"
                            valueRole: "id"
                            model: [
                                { id: "auto", label: "Auto" },
                                { id: "on", label: "On" },
                                { id: "off", label: "Off" }
                            ]
                            currentIndex: {
                                for (let i = 0; i < model.length; i++)
                                    if (model[i].id === appBridge.translationMemoryMode) return i
                                return 0
                            }
                            onActivated: appBridge.translationMemoryMode = currentValue
                        }
                        Item { Layout.fillWidth: true }
                    }

                    SettingsRow {
                        label: "Glossary"
                        CompactTextField {
                            id: glossaryField
                            Layout.fillWidth: true
                            text: appBridge.glossaryPath
                            placeholderText: "No glossary selected"
                            label: "Glossary file"
                            onEditingFinished: appBridge.glossaryPath = appBridge.localPath(text)
                        }
                        AppButton {
                            text: "Choose"
                            small: true
                            iconName: "folder"
                            onClicked: glossaryDialog.open()
                            Accessible.name: "Choose the glossary file"
                        }
                    }

                    SettingsRow {
                        label: "Foreignization"
                        Chip { text: "Always on"; tone: "acc"; iconName: "check" }
                        Item { Layout.fillWidth: true }
                    }

                    SettingsRow {
                        label: "Strict quality gate"
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
                        AppSwitch {
                            text: appBridge.contextSummary ? "Enabled" : "Disabled"
                            checked: appBridge.contextSummary
                            onToggled: appBridge.contextSummary = checked
                            accessibleName: "Rolling scene summary"
                        }
                        Item { Layout.fillWidth: true }
                    }

                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

                    SettingsRow {
                        label: "Cloud base URL"
                        CompactTextField {
                            Layout.fillWidth: true
                            text: appBridge.baseUrl
                            placeholderText: "from .env when blank"
                            label: "Cloud base URL"
                            onEditingFinished: appBridge.baseUrl = text
                        }
                    }

                    SettingsRow {
                        label: "Cloud model"
                        CompactTextField {
                            Layout.fillWidth: true
                            text: appBridge.model
                            placeholderText: "from .env when blank"
                            label: "Cloud model"
                            onEditingFinished: appBridge.model = text
                        }
                    }

                    SettingsRow {
                        label: "API key"
                        hint: "Never persisted to disk."
                        CompactTextField {
                            Layout.fillWidth: true
                            text: appBridge.apiKey
                            echoMode: TextInput.Password
                            placeholderText: "from .env when blank"
                            label: "Cloud API key"
                            onEditingFinished: appBridge.apiKey = text
                        }
                    }

                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

                    SettingsRow {
                        label: "Local model path"
                        CompactTextField {
                            Layout.fillWidth: true
                            text: appBridge.localModel
                            placeholderText: "auto-detected from the models folder"
                            label: "Local translation model path"
                            onEditingFinished: appBridge.localModel = text
                        }
                        Chip {
                            text: appBridge.localModelReady ? "ready" : "missing"
                            tone: appBridge.localModelReady ? "ok" : "warn"
                        }
                    }

                    SettingsRow {
                        label: "llama.cpp threads"
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
                        AppSwitch {
                            text: appBridge.localMlock ? "Enabled" : "Disabled"
                            checked: appBridge.localMlock
                            onToggled: appBridge.localMlock = checked
                            accessibleName: "Lock the local model in RAM"
                        }
                        Item { Layout.fillWidth: true }
                    }
                }

                // ========================================= TRANSCRIPTION ====
                AppCard {
                    id: transcriptionCard
                    Layout.fillWidth: true
                    visible: root._show("transcription asr whisper sensevoice vad ffmpeg spoken language segment silence noise cue budget tags audio")

                    headerExtra: [
                        Pill {
                            tone: appBridge.asrModelReady ? "ok" : "warn"
                            text: appBridge.asrModelReady ? "SenseVoice + VAD installed" : "ASR models missing"
                        }
                    ]

                    SettingsRow {
                        label: "Spoken language"
                        CompactComboBox {
                            Layout.preferredWidth: 200
                            editable: true
                            label: "Spoken language"
                            editText: appBridge.asrLanguage
                            model: ["auto", "ja", "zh", "zh-TW", "ko", "yue", "en"]
                            onAccepted: appBridge.asrLanguage = editText.trim()
                            onActivated: appBridge.asrLanguage = editText.trim()
                        }
                        Item { Layout.fillWidth: true }
                    }

                    SettingsRow {
                        label: "FFmpeg preprocess"
                        CompactComboBox {
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
                            currentIndex: {
                                for (let i = 0; i < model.length; i++)
                                    if (model[i].id === appBridge.asrPreprocess) return i
                                return 0
                            }
                            onActivated: appBridge.asrPreprocess = currentValue
                        }
                        Item { Layout.fillWidth: true }
                    }

                    SettingsRow {
                        label: "Threads"
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
                        CompactTextField {
                            Layout.preferredWidth: 88
                            text: appBridge.asrMinSilenceS
                            label: "Minimum silence (s)"
                            onEditingFinished: appBridge.asrMinSilenceS = text
                        }
                        Label { text: "s"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                        Item { Layout.fillWidth: true }
                    }

                    SettingsRow {
                        label: "Cue budget"
                        CompactTextField {
                            Layout.preferredWidth: 88
                            text: appBridge.asrMaxCueDurationMs
                            label: "Maximum cue duration (ms)"
                            validator: IntValidator { bottom: 500; top: 20000 }
                            onEditingFinished: appBridge.asrMaxCueDurationMs = text
                        }
                        Label { text: "ms"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                        CompactTextField {
                            Layout.preferredWidth: 88
                            text: appBridge.asrMaxCueChars
                            label: "Maximum cue characters"
                            validator: IntValidator { bottom: 10; top: 400 }
                            onEditingFinished: appBridge.asrMaxCueChars = text
                        }
                        Label { text: "chars"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                        CompactTextField {
                            Layout.preferredWidth: 88
                            text: appBridge.asrMaxCueCharsCjk
                            label: "Maximum CJK cue characters"
                            validator: IntValidator { bottom: 5; top: 200 }
                            onEditingFinished: appBridge.asrMaxCueCharsCjk = text
                        }
                        Label { text: "CJK"; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
                        Item { Layout.fillWidth: true }
                    }

                    SettingsRow {
                        label: "Speech / noise"
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
                        CompactTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrBin
                            placeholderText: "bundled when blank"
                            label: "ASR binary path"
                            onEditingFinished: appBridge.asrBin = text
                        }
                    }

                    SettingsRow {
                        label: "VAD binary"
                        CompactTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrVadBin
                            placeholderText: "bundled when blank"
                            label: "VAD binary path"
                            onEditingFinished: appBridge.asrVadBin = text
                        }
                    }

                    SettingsRow {
                        label: "ASR model"
                        CompactTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrModel
                            placeholderText: "auto-detected from the models folder"
                            label: "ASR model path"
                            onEditingFinished: appBridge.asrModel = text
                        }
                    }

                    SettingsRow {
                        label: "VAD model"
                        CompactTextField {
                            Layout.fillWidth: true
                            text: appBridge.asrVadModel
                            placeholderText: "auto-detected from the models folder"
                            label: "VAD model path"
                            onEditingFinished: appBridge.asrVadModel = text
                        }
                    }
                }

                // ============================================ MODELS ========
                AppCard {
                    id: modelsCard
                    Layout.fillWidth: true
                    visible: root._show("models storage download gguf disk cache translation memory purge folder size files")

                    headerExtra: [
                        Chip {
                            text: appBridge.modelsUsedText + " used"
                            mono: true
                        }
                    ]

                    ColumnLayout {
                        width: parent.width
                        spacing: 8

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

                                Label { text: "FILE"; Layout.fillWidth: true; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                Label { text: "SIZE"; Layout.preferredWidth: 96; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                Label { text: "PURPOSE"; Layout.preferredWidth: 110; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                Label { text: "STATE"; Layout.preferredWidth: 110; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                                Label { text: ""; Layout.preferredWidth: 116; color: Theme.textMuted; font.pixelSize: 10 }
                            }
                        }

                        Repeater {
                            model: appBridge.modelsInventory

                            delegate: Rectangle {
                                id: modelRow
                                required property var modelData

                                Layout.fillWidth: true
                                implicitHeight: 32
                                radius: Theme.radiusXs
                                color: modelHover.hovered ? Theme.surfaceAlt : "transparent"

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 10
                                    anchors.rightMargin: 10
                                    spacing: 8

                                    Label {
                                        Layout.fillWidth: true
                                        text: modelRow.modelData.file
                                        color: Theme.textDim
                                        font.pixelSize: Theme.fontTiny
                                        font.family: Theme.monoFont
                                        elide: Text.ElideMiddle
                                    }

                                    Label {
                                        Layout.preferredWidth: 96
                                        text: modelRow.modelData.size
                                        color: Theme.textMuted
                                        font.pixelSize: Theme.fontTiny
                                        font.family: Theme.monoFont
                                    }

                                    Label {
                                        Layout.preferredWidth: 110
                                        text: modelRow.modelData.purpose
                                        color: Theme.textMuted
                                        font.pixelSize: Theme.fontTiny
                                    }

                                    Chip {
                                        Layout.preferredWidth: 110
                                        text: modelRow.modelData.state
                                        tone: modelRow.modelData.tone
                                        iconName: modelRow.modelData.tone === "ok" ? "check" : "alert"
                                        mono: true
                                    }

                                    RowLayout {
                                        Layout.preferredWidth: 116
                                        spacing: 6

                                        AppButton {
                                            text: modelRow.modelData.tone === "ok" ? "Re-download" : "Download"
                                            small: true
                                            variant: modelRow.modelData.tone === "ok" ? "ghost" : "primary"
                                            enabled: !appBridge.isRunning
                                            onClicked: modelRow.modelData.action === "asr"
                                                     ? appBridge.downloadAsrModels()
                                                     : appBridge.downloadLocalModel()
                                        }
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
                                text: appBridge.modelsFolder
                                color: Theme.textMuted
                                font.pixelSize: Theme.fontTiny
                                font.family: Theme.monoFont
                                elide: Text.ElideMiddle
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
                                enabled: appBridge.resultReady || appBridge.logText !== ""
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
                    }
                }

                // ============================================ SHORTCUTS =====
                AppCard {
                    id: shortcutsCard
                    Layout.fillWidth: true
                    visible: root._show("shortcuts keyboard keys ctrl hotkeys")

                    ColumnLayout {
                        width: parent.width
                        spacing: 7

                        Repeater {
                            model: root.shortcutRows

                            delegate: KeyValue {
                                required property var modelData
                                key: modelData.k
                                value: modelData.v
                                mono: true
                            }
                        }
                    }
                }

                // =========================================== ENVIRONMENT ====
                AppCard {
                    id: environmentCard
                    Layout.fillWidth: true
                    visible: root._show("environment paths runtime python qt frozen debug log settings registry diagnostics")

                    ColumnLayout {
                        width: parent.width
                        spacing: 7

                        Repeater {
                            model: appBridge.environmentRows

                            delegate: KeyValue {
                                required property var modelData
                                key: modelData.k
                                value: modelData.v
                                mono: modelData.mono === true
                            }
                        }
                    }
                }

                // =============================================== PRIVACY ====
                AppCard {
                    id: privacyCard
                    Layout.fillWidth: true
                    visible: root._show("data privacy network offline api key settings stored debug log clear reset")

                    ColumnLayout {
                        width: parent.width
                        spacing: 9

                        KeyValue { key: "Network calls in Offline"; value: "none" }
                        KeyValue { key: "API key persisted"; value: "never" }
                        KeyValue { key: "Settings stored in"; value: "QSettings (registry)"; mono: true }
                        KeyValue { key: "Debug log"; value: "debug.log, rotated"; mono: true }

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

                            AppButton {
                                text: "Clear stored settings"
                                small: true
                                variant: "danger"
                                iconName: "x"
                                onClicked: clearDialog.open()
                            }
                        }
                    }
                }

                // ================================================= ABOUT ====
                AppCard {
                    id: aboutCard
                    Layout.fillWidth: true
                    visible: root._show("about version documentation readme help licence build")

                    ColumnLayout {
                        width: parent.width
                        spacing: 9

                        KeyValue { key: "Translation Agent"; value: appBridge.appVersion }
                        KeyValue { key: "Interface"; value: "Subtitle Studio"; mono: true }
                        KeyValue { key: "Target language"; value: "English (locked)" }

                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.borderSoft }

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
                                onClicked: appBridge.copyToClipboard(appBridge.copySummaryText())
                            }

                            Item { Layout.fillWidth: true }
                        }
                    }
                }

                Item { Layout.preferredHeight: 1 }
            }
        }
    }

    readonly property var shortcutRows: [
        { k: "Run a translation", v: "Ctrl Enter" },
        { k: "Cancel the run", v: "Ctrl ." },
        { k: "Go to Run", v: "Ctrl 1" },
        { k: "Go to Review", v: "Ctrl 2" },
        { k: "Go to Quality", v: "Ctrl 3" },
        { k: "Go to Log", v: "Ctrl L" },
        { k: "Go to Settings", v: "Ctrl ," },
        { k: "Save edited subtitles", v: "Ctrl S" },
        { k: "Search cues", v: "Ctrl F" },
        { k: "Command palette", v: "Ctrl K" },
        { k: "Next / previous cue", v: "\u2191 \u2193" }
    ]

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

    Dialog {
        id: clearDialog
        modal: true
        title: "Clear every stored setting?"
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: appBridge.clearStoredSettings()

        Label {
            width: 380
            wrapMode: Text.WordWrap
            text: "Resets the theme, paths, ASR options and pipeline mode to their defaults. "
                  + "Subtitle files and downloaded models are not touched. "
                  + "Restart the app to see every default restored."
            color: Theme.text
            font.pixelSize: Theme.fontBody
        }
    }
}
