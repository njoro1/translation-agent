import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// The top bar's single derived status mirror (UI review 3.1).
//
// Read-only by construction: no MouseArea, no `onClicked`, no action verb in
// the text. A pill is status; controls edit (Corollary 1.2). This replaces the
// scattered `Ready` / `Strict gate off` / `No report yet` pills, which were
// independent widgets that could disagree with each other and with the store.
//
// The line is composed in Python (`AppBridge.globalStatusText`) so it is
// testable and so it always reflects one source of truth.
Item {
    id: root

    readonly property string tone: appBridge.globalStatusTone
    readonly property string label: appBridge.globalStatusText

    implicitWidth: row.implicitWidth + 20
    implicitHeight: 26

    Rectangle {
        anchors.fill: parent
        radius: 999
        color: Theme.toneTint(root.tone)
        border.width: 1
        border.color: Theme.toneBorder(root.tone)
    }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: 8

        // The dot uses the §2.1 vocabulary; the tone is never the only signal
        // because the text says the same thing.
        Rectangle {
            Layout.preferredWidth: 7
            Layout.preferredHeight: 7
            radius: 3.5
            color: Theme.toneColor(root.tone)

            SequentialAnimation on opacity {
                running: appBridge.isRunning && !Theme.reducedMotion
                loops: Animation.Infinite
                NumberAnimation { to: 0.25; duration: 600 }
                NumberAnimation { to: 1.0; duration: 600 }
            }
        }

        Label {
            text: root.label
            color: Theme.textDim
            font.pixelSize: Theme.fontSmall
            elide: Text.ElideRight
            Layout.maximumWidth: 520
        }
    }

    ToolTip.visible: hoverHandler.hovered && row.width > 500
    ToolTip.delay: 500
    ToolTip.text: root.label
    HoverHandler { id: hoverHandler }

    Accessible.role: Accessible.StaticText
    Accessible.name: "Status: " + root.label
}
