import QtQuick
import QtQuick.Controls
import ".."

// Dropdown matching the mockup's `.select` (inset background, chevron).
//
// Deliberately still a ComboBox: the YouTube codec/resolution regression test
// drives ``currentIndex`` + ``activated`` on the real control, and the bridge
// writes must keep flowing through.
ComboBox {
    id: root

    // Optional human label for screen readers / test hooks.
    property string label: ""
    property bool compact: false

    font.pixelSize: Theme.fontBody
    height: compact ? Theme.controlHeightSmall : Theme.controlHeight
    leftPadding: 10
    rightPadding: 26

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
        implicitHeight: root.height
        radius: Theme.radiusSm
        color: Theme.inset
        border.width: 1
        border.color: root.activeFocus || root.popup.visible ? Theme.accentLine
                                                             : (root.hovered ? Theme.borderStrong : Theme.border)
    }

    contentItem: Text {
        leftPadding: root.leftPadding
        rightPadding: root.rightPadding
        text: root.displayText
        color: root.enabled ? Theme.text : Theme.textMuted
        font.pixelSize: Theme.fontBody
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: Icon {
        x: root.width - width - 9
        y: (root.height - height) / 2
        width: 13
        height: 13
        name: "chevron"
        color: Theme.textMuted
        strokeWidth: 2.0
    }

    delegate: ItemDelegate {
        id: itemDelegate
        required property var model
        required property var modelData
        required property int index
        width: root.width
        height: 30
        // ComboBox does not populate `text` on a custom delegate; bind it to
        // the model explicitly (object models use textRole, arrays use modelData).
        text: root.textRole ? model[root.textRole] : modelData
        highlighted: root.highlightedIndex === index

        contentItem: Label {
            text: itemDelegate.text
            color: itemDelegate.highlighted ? Theme.text : Theme.textDim
            font.pixelSize: Theme.fontBody
            verticalAlignment: Text.AlignVCenter
            leftPadding: 8
            elide: Text.ElideRight
        }
        background: Rectangle {
            color: itemDelegate.highlighted ? Theme.surfaceRaised : "transparent"
            radius: Theme.radiusXs
        }
    }

    popup: Popup {
        y: root.height + 2
        width: root.width
        padding: 4
        background: Rectangle {
            color: Theme.surface
            border.color: Theme.borderStrong
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
