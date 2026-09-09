import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Rectangle {
    id: root

    color: "#0D1219"
    height: Theme.headerHeight

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.lg
        anchors.rightMargin: Theme.lg
        spacing: Theme.md

        // Compact app title
        RowLayout {
            spacing: Theme.sm

            Rectangle {
                implicitWidth: 26
                implicitHeight: 26
                radius: 8
                color: Theme.accent

                Label {
                    anchors.centerIn: parent
                    text: "T"
                    color: "#FFFFFF"
                    font.pixelSize: Theme.fontLabel
                    font.bold: true
                }
            }

            Label {
                text: "Translation Agent"
                color: Theme.text
                font.pixelSize: Theme.fontLabel
                font.bold: true
            }
        }

        ModePicker {}

        Item { Layout.fillWidth: true }

        PresetPicker {
            objectName: "presetPicker"
            Layout.preferredWidth: 118
        }

        FieldLabel {
            text: window.isYouTubeMode ? "Source language" : "Spoken language"
        }

        // Light / dark theme toggle (S-02).
        Button {
            id: themeToggle
            implicitWidth: 32
            implicitHeight: 28
            onClicked: appBridge.toggleTheme()
            Accessible.name: Theme.isDark ? "Switch to light theme" : "Switch to dark theme"
            background: Rectangle {
                radius: Theme.radiusSm
                color: themeToggle.hovered ? Theme.surfaceAlt : "transparent"
                border.color: Theme.border
            }
            contentItem: Label {
                text: Theme.isDark ? "\u2600" : "\u263E"
                color: Theme.text
                font.pixelSize: Theme.fontLabel
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            ToolTip.visible: hovered
            ToolTip.delay: 400
            ToolTip.text: Theme.isDark ? "Switch to the light theme" : "Switch to the dark theme"
        }

        CompactComboBox {
            id: langCombo
            Layout.preferredWidth: 102
            editable: true
            editText: window.isYouTubeMode ? appBridge.sourceLang : appBridge.asrLanguage
            model: ["auto", "ja", "zh", "zh-TW", "ko", "yue", "en"]
            onAccepted: window.isYouTubeMode
                       ? (appBridge.sourceLang = langCombo.editText.trim())
                       : (appBridge.asrLanguage = langCombo.editText.trim())
            onActivated: window.isYouTubeMode
                       ? (appBridge.sourceLang = langCombo.editText.trim())
                       : (appBridge.asrLanguage = langCombo.editText.trim())
            ToolTip.visible: hovered
            ToolTip.delay: 500
            ToolTip.text: window.isYouTubeMode
                ? "Source language of the subtitles to translate (auto = detect)."
                : "Spoken language the ASR transcribes (auto = detect). The translation source defaults to this; override it in Advanced."
            Accessible.name: window.isYouTubeMode ? "Source language" : "Spoken language"
        }

        RunButton {
            objectName: "runButton"
        }

        StatusPill {}
    }
}
