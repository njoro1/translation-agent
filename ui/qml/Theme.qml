pragma Singleton
import QtQuick

// Design tokens for the "Subtitle Studio" redesign.
//
// Every visual value lives here so the whole UI can change appearance from one
// place, and so the QML maps 1:1 onto the mockups in ``mockups/assets/mock.css``.
//
// Two axes are pushed in from Main.qml (a singleton cannot reliably read the
// ``appBridge`` context property):
//   * themeName   - "dark" (default) | "light"
//   * comfortable - larger hit targets and +2px text
//   * reducedMotion - pulsing dots and sliding bars stop
//   * accentName  - one of ``accentChoices``; picks the brand hue
QtObject {
    // --- Appearance mode -------------------------------------------------
    property string themeName: "dark"
    readonly property bool isDark: themeName !== "light"

    property bool comfortable: false
    readonly property int fontBoost: comfortable ? 2 : 0

    property bool reducedMotion: false

    // --- Accent presets ---------------------------------------------------
    // The Settings page shows these as swatches. ``accentName`` is persisted by
    // the bridge; everything else derives from it.
    readonly property var accentChoices: [
        { id: "iris",   label: "Iris",   dark: "#7C5CFF", light: "#5B3DF5" },
        { id: "azure",  label: "Azure",  dark: "#4EA8FF", light: "#1F6FD0" },
        { id: "mint",   label: "Mint",   dark: "#3DD68C", light: "#12945C" },
        { id: "amber",  label: "Amber",  dark: "#F5A623", light: "#B26A00" },
        { id: "rose",   label: "Rose",   dark: "#FF5F6D", light: "#D0303F" }
    ]
    property string accentName: "iris"

    function _accentFor(name, dark) {
        for (let i = 0; i < accentChoices.length; i++) {
            if (accentChoices[i].id === name)
                return dark ? accentChoices[i].dark : accentChoices[i].light
        }
        return dark ? "#7C5CFF" : "#5B3DF5"
    }

    // --- Spacing scale (4px base) ----------------------------------------
    readonly property int xs: 4
    readonly property int sm: 8
    readonly property int md: 12
    readonly property int lg: 16
    readonly property int xl: 24
    readonly property int xxl: 32

    // --- Radii ------------------------------------------------------------
    readonly property int radiusXs: 6
    readonly property int radiusSm: 8
    readonly property int radiusMd: 10
    readonly property int radiusLg: 12
    readonly property int radiusXl: 16

    // --- Type scale (10.5 / 11.5 / 12.5 / 13 / 15 / 19 / 22) --------------
    readonly property int fontTiny: 11 + fontBoost
    readonly property int fontSmall: 12 + fontBoost
    readonly property int fontBody: 13 + fontBoost
    readonly property int fontLabel: 14 + fontBoost
    readonly property int fontTitle: 15 + fontBoost
    readonly property int fontH2: 19 + fontBoost
    readonly property int fontH1: 22 + fontBoost

    // --- Surfaces ---------------------------------------------------------
    readonly property color background: isDark ? "#0A0C11" : "#F5F6FA"
    readonly property color backgroundGlow: isDark
        ? Qt.rgba(0.486, 0.361, 1.0, 0.07) : Qt.rgba(0.357, 0.239, 0.961, 0.06)
    readonly property color surface: isDark ? "#12161E" : "#FFFFFF"
    readonly property color surfaceAlt: isDark ? "#161B25" : "#F3F5FA"
    readonly property color surfaceRaised: isDark ? "#1C2230" : "#E9EDF6"
    readonly property color inset: isDark ? "#0C0F15" : "#F1F3F9"
    // The old name for the app-chrome band, kept so nothing that still refers
    // to it breaks.
    readonly property color headerBackground: isDark ? "#12161E" : "#FFFFFF"
    readonly property color border: isDark ? "#242B3A" : "#DCE1EC"
    readonly property color borderSoft: isDark ? "#1B2130" : "#E7EBF3"
    readonly property color borderStrong: isDark ? "#2E3749" : "#C6CEDE"

    // --- Text -------------------------------------------------------------
    readonly property color text: isDark ? "#E9ECF3" : "#11141B"
    readonly property color textDim: isDark ? "#A7B0C2" : "#4B5468"
    readonly property color textMuted: isDark ? "#6E7891" : "#7C8698"

    // --- Brand / semantics ------------------------------------------------
    readonly property color accent: _accentFor(accentName, isDark)
    readonly property color accentHover: Qt.lighter(accent, isDark ? 1.18 : 1.12)
    readonly property color accentInk: "#FFFFFF"
    // Legacy alias used by older call sites.
    readonly property color accentText: accentInk
    readonly property color accentSoft: Qt.rgba(accent.r, accent.g, accent.b, isDark ? 0.14 : 0.10)
    readonly property color accentLine: Qt.rgba(accent.r, accent.g, accent.b, isDark ? 0.38 : 0.35)

    readonly property color success: isDark ? "#3DD68C" : "#12945C"
    readonly property color warning: isDark ? "#F5A623" : "#B26A00"
    readonly property color error: isDark ? "#FF5F6D" : "#D0303F"
    readonly property color info: isDark ? "#4EA8FF" : "#1F6FD0"

    readonly property color errorHover: Qt.lighter(error, 1.12)
    readonly property color warningHover: Qt.lighter(warning, 1.12)

    readonly property color successTint: Qt.rgba(success.r, success.g, success.b, isDark ? 0.13 : 0.11)
    readonly property color warningTint: Qt.rgba(warning.r, warning.g, warning.b, isDark ? 0.13 : 0.11)
    readonly property color errorTint: Qt.rgba(error.r, error.g, error.b, isDark ? 0.13 : 0.10)
    readonly property color infoTint: Qt.rgba(info.r, info.g, info.b, isDark ? 0.13 : 0.10)
    readonly property color accentTint: accentSoft

    // Secret fields (API key) get a recessed background in both themes.
    readonly property color fieldSecretBackground: isDark ? "#0D1117" : "#E3E8F0"

    // --- Fonts ------------------------------------------------------------
    readonly property string monoFont: "Consolas"
    readonly property string uiFont: "Segoe UI"

    // --- Geometry ---------------------------------------------------------
    readonly property int controlHeight: comfortable ? 38 : 34
    readonly property int controlHeightSmall: comfortable ? 32 : 28
    readonly property int rowHeight: comfortable ? 40 : 34
    // Legacy alias: ``fieldHeight`` was the old control height.
    readonly property int fieldHeight: controlHeight
    readonly property int topbarHeight: 56
    readonly property int railWidth: 64
    readonly property int statusbarHeight: 30
    // Legacy alias.
    readonly property int headerHeight: topbarHeight

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

    // Tone name -> colour / tint. Used by pills, chips, tiles and badges so the
    // palette lives in exactly one place.
    function toneColor(tone) {
        if (tone === "ok") return success
        if (tone === "warn") return warning
        if (tone === "err") return error
        if (tone === "info") return info
        if (tone === "acc") return accent
        return textMuted
    }

    function toneTint(tone) {
        if (tone === "ok") return successTint
        if (tone === "warn") return warningTint
        if (tone === "err") return errorTint
        if (tone === "info") return infoTint
        if (tone === "acc") return accentSoft
        return surfaceRaised
    }

    function toneBorder(tone) {
        if (tone === "ok") return Qt.rgba(success.r, success.g, success.b, 0.30)
        if (tone === "warn") return Qt.rgba(warning.r, warning.g, warning.b, 0.30)
        if (tone === "err") return Qt.rgba(error.r, error.g, error.b, 0.30)
        if (tone === "info") return Qt.rgba(info.r, info.g, info.b, 0.30)
        if (tone === "acc") return accentLine
        return border
    }

    // --- Small formatters -------------------------------------------------
    function formatDuration(sec) {
        var s = Math.max(0, Math.floor(sec))
        var m = Math.floor(s / 60)
        var rs = s % 60
        return (m > 0 ? m + "m " : "") + rs + "s"
    }

    function formatClock(sec) {
        var s = Math.max(0, Math.floor(sec))
        var m = Math.floor(s / 60)
        var rs = s % 60
        return m + ":" + (rs < 10 ? "0" : "") + rs
    }
}
