import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// The single primary action of the Run screen (UI review 3.3, 6.6).
//
// Invariants, all of them previously violated:
//   * ONE hue (the accent) — it never recolours per mode. It used to flip
//     purple <-> amber depending on model state.
//   * ONE label grammar — `Run` / `Cancel`. It used to become
//     "Download model & Run" / "Repair model & Run", which clipped to
//     "Download model &…" at the window edge.
//   * It NEVER truncates: the button sizes to its content.
//   * A blocked precondition does NOT redefine the action's identity. The
//     button stays `Run`, goes disabled, and states the reason. Downloading a
//     model is a secondary action inside the Processing panel, not a hijack of
//     the global button.
//
// State mapping:
//   idle + ready      -> "Run"
//   idle + blocked    -> "Run", disabled, reason in the tooltip
//   running           -> "Cancel" (never disabled: a bad run must be stoppable)
//   failed            -> "Run" (retry), reason in the tooltip
Button {
    id: root

    readonly property bool running: appBridge.isRunning
    readonly property string blockedReason: appBridge.runBlockedReason
    readonly property bool blocked: !root.running && root.blockedReason !== ""
    readonly property string iconName: root.running ? "stop" : "play"

    text: root.running ? "Cancel" : "Run"
    enabled: root.running || !root.blocked
    implicitHeight: Theme.controlHeight
    implicitWidth: contentItem.implicitWidth + 30
    padding: 0
    opacity: enabled ? 1 : 0.55

    background: Rectangle {
        radius: Theme.radiusSm
        // One hue family. Cancel uses the accent too — the label says what it
        // does, so the colour does not have to.
        color: {
            if (root.running)
                return root.hovered ? Qt.lighter(Theme.accent, 1.12) : Theme.accent
            if (!root.enabled)
                return Theme.surfaceRaised
            return root.hovered ? Theme.accentHover : Theme.accent
        }
        Behavior on color { ColorAnimation { duration: Theme.reducedMotion ? 0 : 120 } }
    }

    contentItem: RowLayout {
        spacing: 7

        Icon {
            name: root.iconName
            color: root.enabled ? Theme.accentInk : Theme.textMuted
            strokeWidth: 2.0
            Layout.preferredWidth: 15
            Layout.preferredHeight: 15
        }

        Label {
            text: root.text
            color: root.enabled ? Theme.accentInk : Theme.textMuted
            font.pixelSize: Theme.fontBody
            font.bold: true
            verticalAlignment: Text.AlignVCenter
            // Deliberately no `elide`: the label is short by construction and
            // the button sizes to it, so a mid-word cut is impossible.
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
        if (root.blocked)
            return "Run is blocked: " + root.blockedReason
        return "Run the translation pipeline"
    }

    ToolTip.visible: hovered && (root.running || root.blocked)
    ToolTip.delay: 300
    ToolTip.text: {
        if (root.running)
            return "Ask the pipeline to stop after the current batch finishes (cooperative cancel)."
        if (root.blocked)
            return "Run is blocked: " + root.blockedReason
        return ""
    }
}
