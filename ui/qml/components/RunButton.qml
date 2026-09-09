import QtQuick
import QtQuick.Controls
import ".."

Button {
    id: root

    readonly property bool running: appBridge.isRunning
    readonly property bool needsModelDownload: appBridge.pipelineMode === "offline" && !appBridge.localModelReady

    // One dual-purpose control: Run (or Download Model & Run) when idle,
    // a red Stop while a run is active. Never disabled while running —
    // the old build had `enabled: !running`, which made its own cancel
    // branch dead code and left the user unable to stop a bad run.
    text: running ? "Stop" : (needsModelDownload ? "Download Model & Run" : "Run")
    implicitWidth: Math.max(112, contentItem.implicitWidth + 28)
    implicitHeight: 32

    background: Rectangle {
        radius: Theme.radiusSm
        color: {
            if (root.running)
                return root.hovered ? "#DC2626" : "#EF4444"
            if (root.needsModelDownload)
                return root.hovered ? Qt.lighter(Theme.warning, 1.1) : Theme.warning
            return root.hovered ? Theme.accentHover : Theme.accent
        }
        border.color: root.activeFocus ? Theme.text : "transparent"
        border.width: 1
    }

    contentItem: Label {
        text: root.text
        color: "#FFFFFF"
        font.pixelSize: Theme.fontLabel
        font.bold: true
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    onClicked: {
        if (root.running)
            appBridge.cancelRun()
        else
            appBridge.runTranslation()
    }

    Accessible.role: Accessible.Button
    Accessible.name: root.text
    Accessible.description: {
        if (root.running)
            return "Stop the running translation"
        if (root.needsModelDownload)
            return "Download the local model and run the translation"
        return "Run the translation pipeline"
    }

    ToolTip.visible: hovered
    ToolTip.delay: 400
    ToolTip.text: {
        if (root.running)
            return "Ask the pipeline to stop after the current batch finishes (cooperative cancel)."
        if (root.needsModelDownload)
            return "The local translation model is missing; it will be downloaded first."
        return ""
    }
}
