pragma Singleton
import QtQuick

// Design tokens. Every visual value lives here so the whole UI can change
// appearance from one place.
//
// Two axes were added after the UX review:
//   * themeName  - "dark" (default) | "light". A singleton cannot reliably read
//                  a context property such as `appBridge`, so Main.qml pushes
//                  the persisted value in with a Binding instead.
//   * comfortable - larger hit targets and +2px text. The default 30px field /
//                   12px text is too small for long proofreading sessions.
QtObject {
    // --- Appearance mode -------------------------------------------------
    property string themeName: "dark"
    readonly property bool isDark: themeName !== "light"

    property bool comfortable: false
    readonly property int fontBoost: comfortable ? 2 : 0

    // Honour reduced-motion preferences: pulsing dots and sliding bars stop.
    property bool reducedMotion: false

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
    readonly property int fontSmall: 12 + fontBoost
    readonly property int fontBody: 13 + fontBoost
    readonly property int fontLabel: 14 + fontBoost
    readonly property int fontTitle: 16 + fontBoost
    readonly property int fontHeader: 18 + fontBoost

    // Palette (semantic only - never hardcode a colour in a component)
    readonly property color background: isDark ? "#0B0F14" : "#F4F6FA"
    readonly property color headerBackground: isDark ? "#0D1219" : "#E9EEF6"
    readonly property color surface: isDark ? "#11161D" : "#FFFFFF"
    readonly property color surfaceAlt: isDark ? "#161C24" : "#EDF1F7"
    readonly property color border: isDark ? "#20262E" : "#D3DAE5"
    readonly property color text: isDark ? "#E6EAF0" : "#141A21"
    readonly property color textMuted: isDark ? "#8A94A3" : "#5A6675"
    readonly property color accent: isDark ? "#3D82F6" : "#2563EB"
    readonly property color accentHover: isDark ? "#5B96F8" : "#1D4ED8"
    readonly property color success: isDark ? "#22C55E" : "#15803D"
    readonly property color warning: isDark ? "#F59E0B" : "#B45309"
    readonly property color error: isDark ? "#EF4444" : "#B91C1C"
    readonly property color errorHover: isDark ? "#DC2626" : "#991B1B"
    readonly property color warningHover: isDark ? "#D97706" : "#92400E"

    // Text drawn on top of a filled accent/error button.
    readonly property color accentText: "#FFFFFF"

    // Secret fields (API key) get a recessed background in both themes.
    readonly property color fieldSecretBackground: isDark ? "#0D1117" : "#E3E8F0"

    // Derived tints
    readonly property color errorTint: isDark
        ? Qt.rgba(0.937, 0.267, 0.267, 0.12) : Qt.rgba(0.725, 0.110, 0.110, 0.10)
    readonly property color warningTint: isDark
        ? Qt.rgba(0.961, 0.620, 0.043, 0.10) : Qt.rgba(0.706, 0.420, 0.035, 0.12)
    readonly property color successTint: isDark
        ? Qt.rgba(0.133, 0.773, 0.369, 0.10) : Qt.rgba(0.082, 0.502, 0.239, 0.12)
    readonly property color accentTint: isDark
        ? Qt.rgba(0.239, 0.510, 0.965, 0.15) : Qt.rgba(0.145, 0.388, 0.922, 0.12)

    // Controls. 32px default (up from 30) and 36px in comfortable mode.
    readonly property int fieldHeight: comfortable ? 36 : 32
    readonly property int rowHeight: comfortable ? 40 : 34
    readonly property int headerHeight: 56

    // --- Status helpers ---------------------------------------------------
    // Row state must never rely on colour alone (WCAG 1.4.1), so every status
    // carries an icon and a word as well as a colour.
    function statusIcon(status) {
        if (status === "untranslated" || status === "empty") return "!"
        if (status === "warning") return "\u25B2"
        return "\u2713"
    }

    function statusLabel(status) {
        if (status === "untranslated") return "Untranslated"
        if (status === "empty") return "Empty"
        if (status === "warning") return "Warning"
        return "OK"
    }

    function statusColor(status) {
        if (status === "untranslated" || status === "empty") return error
        if (status === "warning") return warning
        return success
    }

    function statusTint(status) {
        if (status === "untranslated" || status === "empty") return errorTint
        if (status === "warning") return warningTint
        return successTint
    }
}
