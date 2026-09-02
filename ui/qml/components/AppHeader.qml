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

        PresetPicker {
            objectName: "presetPicker"
            Layout.preferredWidth: 128
        }

        CompactComboBox {
            id: langCombo
            Layout.preferredWidth: 96
            editable: true
            editText: appBridge.sourceLang
            model: ["", "ja", "zh", "zh-TW", "ko", "yue", "en"]
            onAccepted: appBridge.sourceLang = editText.trim()
            onActivated: appBridge.sourceLang = editText.trim()
            ToolTip.visible: hovered
            ToolTip.delay: 500
            ToolTip.text: "Source language hint (blank = auto-detect)."
        }

        Item { Layout.fillWidth: true }

        RunButton {}

        StatusPill {}
    }
}
