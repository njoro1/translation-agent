pragma Singleton
import QtQuick

QtObject {
    // Spacing scale
    readonly property int xs: 4
    readonly property int sm: 8
    readonly property int md: 12
    readonly property int lg: 16
    readonly property int xl: 24

    // Radii
    readonly property int radiusSm: 6
    readonly property int radiusMd: 8
    readonly property int radiusLg: 10

    // Type scale
    readonly property int fontSmall: 12
    readonly property int fontBody: 13
    readonly property int fontLabel: 14
    readonly property int fontTitle: 16
    readonly property int fontHeader: 18

    // Palette
    readonly property color background: "#0B0F14"
    readonly property color surface: "#11161D"
    readonly property color surfaceAlt: "#161C24"
    readonly property color border: "#20262E"
    readonly property color text: "#E6EAF0"
    readonly property color textMuted: "#8A94A3"
    readonly property color accent: "#3D82F6"
    readonly property color accentHover: "#5B96F8"
    readonly property color success: "#22C55E"
    readonly property color warning: "#F59E0B"
    readonly property color error: "#EF4444"

    // Derived tints
    readonly property color errorTint: Qt.rgba(0.937, 0.267, 0.267, 0.12)
    readonly property color warningTint: Qt.rgba(0.961, 0.620, 0.043, 0.10)
    readonly property color successTint: Qt.rgba(0.133, 0.773, 0.369, 0.10)

    readonly property int fieldHeight: 30
    readonly property int headerHeight: 56
}
