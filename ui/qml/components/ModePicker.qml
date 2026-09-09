import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Segmented pipeline-mode selector: YouTube Cloud | Local Cloud | Offline.
RowLayout {
    id: root

    spacing: 0

    readonly property var modes: [
        { id: "youtube_cloud", label: "YouTube Cloud" },
        { id: "local_cloud", label: "Local Cloud" },
        { id: "offline", label: "Offline" }
    ]

    Repeater {
        model: root.modes

        delegate: Button {
            id: segment
            required property var modelData
            required property int index

            Layout.preferredWidth: 108
            Layout.preferredHeight: 30
            checkable: true
            checked: appBridge.pipelineMode === modelData.id

            background: Rectangle {
                radius: index === 0 ? Theme.radiusSm : (index === root.modes.length - 1 ? Theme.radiusSm : 0)
                color: segment.checked ? Theme.accent : Theme.surfaceAlt
                border.color: Theme.border
                border.width: 1
            }

            contentItem: Label {
                text: segment.modelData.label
                color: segment.checked ? "#FFFFFF" : Theme.textMuted
                font.pixelSize: Theme.fontSmall
                font.bold: segment.checked
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }

            onClicked: appBridge.setPipelineMode(modelData.id)

            ToolTip.visible: hovered
            ToolTip.delay: 500
            ToolTip.text: {
                if (modelData.id === "youtube_cloud")
                    return "Fetch YouTube subtitles, translate with a cloud LLM."
                if (modelData.id === "local_cloud")
                    return "Transcribe a local file with local ASR, translate with a cloud LLM."
                return "Transcribe and translate fully offline (no cloud)."
            }
        }
    }
}
