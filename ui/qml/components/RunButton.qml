import QtQuick
import QtQuick.Controls
import ".."

Button {
    id: root

    property bool running: appBridge.isRunning
    property bool needsModelDownload: appBridge.pipelineMode === "offline" && !appBridge.localModelReady

    text: running ? "Runningâ€¦" : (needsModelDownload ? "Download Model & Run" : "Run")
    enabled: !running
    implicitWidth: Math.max(120, contentItem.implicitWidth + 28)
    implicitHeight: 32

    background: Rectangle {
        radius: Theme.radiusSm
        color: {
            if (!root.enabled) return Theme.surfaceAlt
            if (root.needsModelDownload && !root.running) return Theme.warning
            return root.hovered ? Theme.accentHover : Theme.accent
        }
        border.color: root.activeFocus ? Theme.text : "transparent"
        border.width: 1
    }

    contentItem: Label {
        text: root.text
        color: root.enabled ? "#FFFFFF" : Theme.textMuted
        font.pixelSize: Theme.fontLabel
        font.bold: true
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    onClicked: appBridge.runTranslation()

    ToolTip.visible: hovered && needsModelDownload
    ToolTip.delay: 400
    ToolTip.text: "The local translation model is missing; it will be downloaded first."
}
