import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// The single button used everywhere.
// variants: default | primary | danger | ghost | link
Button {
    id: root

    property string variant: "default"
    property bool small: false
    property string iconName: ""
    property int iconSize: small ? 14 : 15

    readonly property bool _primary: variant === "primary"
    readonly property bool _danger: variant === "danger"
    readonly property bool _ghost: variant === "ghost"
    readonly property bool _link: variant === "link"
    readonly property bool _bordered: !(_primary || _danger || _ghost || _link)

    readonly property color labelColor: {
        if (!enabled) return Theme.textMuted
        if (_primary) return Theme.accentInk
        if (_danger) return Theme.error
        if (_link) return Theme.accent
        if (_ghost) return hovered ? Theme.text : Theme.textDim
        return Theme.text
    }

    implicitHeight: small ? Theme.controlHeightSmall : Theme.controlHeight
    implicitWidth: Math.max(contentItem.implicitWidth + (small ? 22 : 28),
                            small ? Theme.controlHeightSmall : Theme.controlHeight)
    padding: 0
    opacity: enabled ? 1.0 : 0.45

    background: Rectangle {
        radius: root.small ? Theme.radiusXs : Theme.radiusSm
        color: {
            if (root._primary) return root.hovered ? Theme.accentHover : Theme.accent
            if (root._danger) return root.hovered ? Qt.rgba(Theme.error.r, Theme.error.g, Theme.error.b, 0.22)
                                                  : Theme.errorTint
            if (root._ghost || root._link) return root.hovered ? Theme.surfaceAlt : "transparent"
            return root.hovered ? Theme.surfaceRaised : Theme.surfaceAlt
        }
        border.width: root._bordered || root._danger ? 1 : 0
        border.color: root._danger
                      ? Qt.rgba(Theme.error.r, Theme.error.g, Theme.error.b, 0.35)
                      : Theme.border
        Behavior on color { ColorAnimation { duration: Theme.reducedMotion ? 0 : 120 } }
    }

    contentItem: RowLayout {
        spacing: 7

        Icon {
            visible: root.iconName !== ""
            name: root.iconName
            color: root.labelColor
            strokeWidth: 1.8
            Layout.preferredWidth: root.iconSize
            Layout.preferredHeight: root.iconSize
        }

        Label {
            text: root.text
            color: root.labelColor
            font.pixelSize: root.small ? Theme.fontSmall : Theme.fontBody
            font.weight: root._primary ? Font.DemiBold : Font.Normal
            verticalAlignment: Text.AlignVCenter
        }
    }

    Accessible.role: Accessible.Button
    Accessible.name: root.text
}
