import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Segmented pipeline-mode selector: YouTube Cloud | Local Cloud | Offline.
// The three modes are a product invariant — there is no fourth "cloud rescue".
Rectangle {
    id: root

    readonly property var modes: [
        { id: "youtube_cloud", label: "YouTube Cloud", icon: "link" },
        { id: "local_cloud", label: "Local Cloud", icon: "file" },
        { id: "offline", label: "Offline", icon: "cpu" }
    ]

    implicitWidth: row.implicitWidth + 8
    implicitHeight: 34
    radius: Theme.radiusMd
    color: Theme.inset
    border.color: Theme.border
    border.width: 1

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 2

        Repeater {
            model: root.modes

            delegate: Item {
                required property var modelData

                readonly property bool isOn: appBridge.pipelineMode === modelData.id

                Layout.preferredWidth: segLabel.implicitWidth + 26
                Layout.preferredHeight: 28

                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radiusXs
                    color: parent.isOn ? Theme.surfaceRaised
                                       : (segMouse.containsMouse ? Theme.surfaceAlt : "transparent")
                }

                RowLayout {
                    anchors.centerIn: parent
                    spacing: 6

                    Icon {
                        name: parent.parent.modelData.icon
                        color: parent.parent.isOn ? Theme.text : Theme.textMuted
                        Layout.preferredWidth: 14
                        Layout.preferredHeight: 14
                    }

                    Label {
                        id: segLabel
                        text: parent.parent.modelData.label
                        color: parent.parent.isOn ? Theme.text : Theme.textMuted
                        font.pixelSize: Theme.fontBody
                        font.bold: parent.parent.isOn
                    }
                }

                MouseArea {
                    id: segMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: appBridge.setPipelineMode(modelData.id)
                }

                ToolTip.visible: segMouse.containsMouse
                ToolTip.delay: 500
                ToolTip.text: {
                    if (modelData.id === "youtube_cloud")
                        return "Fetch YouTube subtitles, translate with a cloud LLM."
                    if (modelData.id === "local_cloud")
                        return "Transcribe a local file with local ASR, translate with a cloud LLM."
                    return "Transcribe and translate fully offline (no cloud)."
                }

                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.label
                Accessible.checked: isOn
            }
        }
    }
}
