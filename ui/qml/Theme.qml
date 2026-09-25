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
    // Every swatch clears WCAG AA (4.5:1) against `accentInk`, in its own theme
    // — that is what makes one ink token legal for all five. `tests/
    // test_theme_contrast.py` re-derives the ratios from this table, so a
    // "prettier" hex that dips below the bar fails the build.
    readonly property var accentChoices: [
        { id: "iris",   label: "Iris",   dark: "#8A6BFF", light: "#5B3DF5" },
        { id: "azure",  label: "Azure",  dark: "#4EA8FF", light: "#1D69C5" },
        { id: "mint",   label: "Mint",   dark: "#3DD68C", light: "#0E7948" },
        { id: "amber",  label: "Amber",  dark: "#F5A623", light: "#985B00" },
        { id: "rose",   label: "Rose",   dark: "#FF5F6D", light: "#C72E3C" }
    ]
    property string accentName: "iris"

    function _accentFor(name, dark) {
        for (let i = 0; i < accentChoices.length; i++) {
            if (accentChoices[i].id === name)
                return dark ? accentChoices[i].dark : accentChoices[i].light
        }
        return dark ? "#8A6BFF" : "#5B3DF5"
    }

    // --- Spacing scale (4px base) ----------------------------------------
    // Density reaches the spacing scale as well as the type scale. Without
    // this, "Comfortable" only grew the text and the controls, so a
    // comfortable window was *tighter* than a compact one — more pixels of
    // glyph in the same gaps. `xs` stays at 4px: it is used for hairline
    // gaps inside a single control, which must not move.
    readonly property int xs: 4
    readonly property int sm: comfortable ? 10 : 8
    readonly property int md: comfortable ? 14 : 12
    readonly property int lg: comfortable ? 20 : 16
    readonly property int xl: comfortable ? 28 : 24
    readonly property int xxl: comfortable ? 38 : 32

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
        ? Qt.rgba(0.541, 0.420, 1.0, 0.07) : Qt.rgba(0.357, 0.239, 0.961, 0.06)
    readonly property color surface: isDark ? "#12161E" : "#FFFFFF"
    readonly property color surfaceAlt: isDark ? "#161B25" : "#F3F5FA"
    readonly property color surfaceRaised: isDark ? "#1C2230" : "#E9EDF6"
    readonly property color inset: isDark ? "#0C0F15" : "#F1F3F9"
    // The old name for the app-chrome band, kept so nothing that still refers
    // to it breaks.
    readonly property color headerBackground: isDark ? "#12161E" : "#FFFFFF"
    readonly property color border: isDark ? "#242B3A" : "#DCE1EC"
    // `borderSoft` is the hairline under a card header. It has to survive the
    // WCAG 1.4.11 non-text bar (>= 1.2:1 against `surface`) or it is not a
    // border, it is a rumour.
    readonly property color borderSoft: isDark ? "#212938" : "#E1E6F0"
    readonly property color borderStrong: isDark ? "#2E3749" : "#C6CEDE"

    // --- Text -------------------------------------------------------------
    // Three steps of the same ramp. All three are read as running text, so all
    // three clear AA (4.5:1) on the *lightest* surface they can land on —
    // `surfaceRaised` in dark, `background` in light. `textMuted` is the
    // helper/placeholder step and is the tightest of the three.
    readonly property color text: isDark ? "#E9ECF3" : "#11141B"
    readonly property color textDim: isDark ? "#A7B0C2" : "#4B5468"
    readonly property color textMuted: isDark ? "#828DA6" : "#5E6779"

    // --- Brand / semantics ------------------------------------------------
    readonly property color accent: _accentFor(accentName, isDark)
    readonly property color accentHover: Qt.lighter(accent, isDark ? 1.18 : 1.12)
    // The label painted *on top of* a filled accent surface — the primary
    // action, the active segment, the error badge. Dark-theme accents are
    // bright pastels (so they read as text on a near-black page), which means
    // white ink lands at 2.0–4.3:1 on them; a near-black ink clears AA on every
    // swatch and on `error` too. Hence the flip rather than a fixed white.
    readonly property color accentInk: isDark ? "#0A0C11" : "#FFFFFF"
    // Legacy alias used by older call sites.
    readonly property color accentText: accentInk
    readonly property color accentSoft: Qt.rgba(accent.r, accent.g, accent.b, isDark ? 0.14 : 0.10)
    readonly property color accentLine: Qt.rgba(accent.r, accent.g, accent.b, isDark ? 0.38 : 0.35)

    // Kept in step with the `mint` / `amber` accent swatches, and dark enough
    // in light theme to be legible as running text (an error title, a warning
    // row), not just as a fill.
    //
    // The light values are set by `surfaceRaised` — the *lightest* surface a
    // status colour lands on, because `Chip` uses it as the background for a
    // toned chip. At the previous values every light status colour sat at
    // 4.2–4.3:1 there, i.e. just under AA. The dark theme has no equivalent
    // problem: its status colours clear 7.8:1 on their worst surface.
    readonly property color success: isDark ? "#3DD68C" : "#0E7948"
    readonly property color warning: isDark ? "#F5A623" : "#985B00"
    readonly property color error: isDark ? "#FF5F6D" : "#C72E3C"
    readonly property color info: isDark ? "#4EA8FF" : "#1D69C5"

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

    // --- Ring treatment for the two "no verdict" states -------------------
    // `unchecked` is an open ring (we have not looked yet). `na` is a closed
    // muted ring with a dash (this mode never uses it). They are different
    // facts and must not collapse into one grey dash — that collapse is what
    // made the readiness denominator disagree with the visible rows, so the
    // pair lives here rather than being re-invented per page.
    function statusRing(status) {
        if (status === "unchecked") return borderStrong
        if (status === "na") return border
        return "transparent"
    }

    function statusRingWidth(status) {
        if (status === "unchecked") return 1.5
        if (status === "na") return 1
        return 0
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
