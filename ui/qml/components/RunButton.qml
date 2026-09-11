import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// One dual-purpose control: the single primary action of the Run screen.
//   * idle              -> "Run"
//   * offline, no model -> "Download model & Run" (auto-downloads first)
//   * running           -> "Cancel" (danger) — never disabled while running, so
//                          a bad run can always be stopped.
Button {
    id: root

    readonly property bool running: appBridge.isRunning
    readonly property bool needsModelDownload: appBridge.pipelineMode === "offline" && !appBridge.localModelReady
    // `Button` owns `icon` (a QQuickIcon), so the glyph name is our own property.
    readonly property string iconName: running ? "stop"
                                              : (needsModelDownload ? "download" : "play")

    text: running ? "Cancel" : (needsModelDownload ? "Download model & Run" : "Run")
    implicitHeight: Theme.controlHeight
    implicitWidth: contentItem.implicitWidth + 30
    padding: 0

    background: Rectangle {
        radius: Theme.radiusSm
        color: {
            if (root.running)
                return root.hovered ? Theme.errorHover : Theme.error
            if (root.needsModelDownload)
                return root.hovered ? Theme.warningHover : Theme.warning
            return root.hovered ? Theme.accentHover : Theme.accent
        }
        Behavior on color { ColorAnimation { duration: Theme.reducedMotion ? 0 : 120 } }
    }

    contentItem: RowLayout {
        spacing: 7

        Icon {
            name: root.iconName
            color: root.running || root.needsModelDownload ? "#FFFFFF" : Theme.accentInk
            strokeWidth: 2.0
            Layout.preferredWidth: 15
            Layout.preferredHeight: 15
        }

        Label {
            text: root.text
            color: root.running || root.needsModelDownload ? "#FFFFFF" : Theme.accentInk
            font.pixelSize: Theme.fontBody
            font.bold: true
            verticalAlignment: Text.AlignVCenter
        }
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
            return "Cancel the running translation"
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
