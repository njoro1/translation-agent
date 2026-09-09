import QtQuick
import QtQuick.Controls
import ".."

ComboBox {
    id: root

    // Optional human label for screen readers / test hooks.
    property string label: ""

    font.pixelSize: Theme.fontBody
    height: Theme.fieldHeight

    Accessible.role: Accessible.ComboBox
    Accessible.name: root.label !== "" ? root.label : root.displayText

    // Test/screenshot hooks: QQuickPopup is not exposed to Python, so the
    // popup is opened/closed through invokable QML functions.
    function openPopupExternally() {
        popup.open()
    }

    function closePopupExternally() {
        popup.close()
    }

    background: Rectangle {
        implicitHeight: Theme.fieldHeight
        radius: Theme.radiusSm
        color: Theme.surfaceAlt
        border.color: root.activeFocus ? Theme.accent : Theme.border
        border.width: 1
    }

    contentItem: Text {
        leftPadding: 8
        rightPadding: root.indicator.width
        text: root.displayText
        color: Theme.text
        font.pixelSize: Theme.fontBody
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: Label {
        x: root.width - width - 8
        y: (root.height - height) / 2
        text: "\u25BC"
        color: Theme.textMuted
        font.pixelSize: 9
    }

    delegate: ItemDelegate {
        id: itemDelegate
        required property var model
        required property var modelData
        required property int index
        width: root.width
        height: 28
        // ComboBox does not populate `text` on a custom delegate; bind it to
        // the model explicitly (object models use textRole, arrays use modelData).
        text: root.textRole ? model[root.textRole] : modelData

        contentItem: Label {
            text: itemDelegate.text
            color: itemDelegate.highlighted ? Theme.text : Theme.textMuted
            font.pixelSize: Theme.fontBody
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        highlighted: root.highlightedIndex === index
        background: Rectangle {
            color: itemDelegate.highlighted ? Theme.surfaceAlt : "transparent"
        }
    }

    popup: Popup {
        y: root.height + 2
        width: root.width
        padding: 1
        background: Rectangle {
            color: Theme.surface
            border.color: Theme.border
            radius: Theme.radiusSm
        }
        contentItem: ListView {
            clip: true
            // Capped: an uncapped contentHeight let long lists (e.g. YouTube
            // resolutions) open a popup taller than the window, putting the
            // last items permanently out of reach.
            implicitHeight: Math.min(contentHeight, 320)
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        }
    }
}
