import QtQuick
import QtQuick.Shapes

// Stroke icon set, ported 1:1 from ``mockups/assets/icons.js``.
//
// Rendered with QtQuick.Shapes (no SVG image plugin needed, so the trimmed
// PyInstaller bundle cannot lose the icon set) on a 24x24 grid.
Item {
    id: root

    property string name: ""
    property color color: Theme.textMuted
    property real strokeWidth: 1.8

    implicitWidth: 16
    implicitHeight: 16

    readonly property real _scale: Math.min(width, height) / 24
    readonly property string _d: root.path(root.name)

    // Icon geometry table. Keys must match the names used across the UI.
    readonly property var _paths: ({
        play:        "M7 4.5v15l13-7.5-13-7.5Z",
        stop:        "M6 6h12v12H6Z",
        pause:       "M9 5v14M15 5v14",
        list:        "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",
        shield:      "M12 3.5 5 6.5v5.2c0 4.3 2.9 7.6 7 8.8 4.1-1.2 7-4.5 7-8.8V6.5l-7-3ZM9 12l2.2 2.2L15.5 10",
        terminal:    "M5 6h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Zm2.5 4 2 2-2 2M12.5 14h4",
        settings:    "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm7.4 6a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2 2 2 0 1 1-4 0 1.7 1.7 0 0 0-2.9-1.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 2.6 15a2 2 0 1 1 0-4 1.7 1.7 0 0 0 1.5-2.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 9.7 4a2 2 0 1 1 4 0 1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.7 1.7 0 0 0 20.9 11a2 2 0 1 1 0 4Z",
        sun:         "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
        moon:        "M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z",
        search:      "M11 4.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13Zm5 11.5 4 4",
        chevron:     "M6 9l6 6 6-6",
        check:       "M5 12.5l4.5 4.5L19 7",
        alert:       "M12 4.5 2.8 20h18.4L12 4.5ZM12 10v4.5M12 17.4h.01",
        x:           "M6 6l12 12M18 6 6 18",
        info:        "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM12 11v5M12 8h.01",
        folder:      "M3 7.5A2 2 0 0 1 5 5.5h3.6l1.8 2.2H19a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7.5Z",
        link:        "M10 13.5a3.5 3.5 0 0 0 5 0l3-3a3.5 3.5 0 0 0-5-5l-1 1M14 10.5a3.5 3.5 0 0 0-5 0l-3 3a3.5 3.5 0 0 0 5 5l1-1",
        file:        "M14 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5l-5-5ZM14 3.5v5h5",
        download:    "M12 4v11M7.5 11l4.5 4.5 4.5-4.5M4.5 19.5h15",
        upload:      "M12 20V9M7.5 13.5 12 9l4.5 4.5M4.5 4.5h15",
        film:        "M3 6.5h18v11H3Z M8 4.5v15M16 4.5v15M3 12h18M3 8.2h5M3 15.8h5M16 8.2h5M16 15.8h5",
        globe:       "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM3.5 12h17M12 3.5c2.4 2.3 3.6 5.2 3.6 8.5s-1.2 6.2-3.6 8.5c-2.4-2.3-3.6-5.2-3.6-8.5S9.6 5.8 12 3.5Z",
        cpu:         "M7 7h10v10H7Z M10 3.5v3M14 3.5v3M10 17.5v3M14 17.5v3M3.5 10h3M3.5 14h3M17.5 10h3M17.5 14h3",
        layers:      "M12 3.5l8.5 4.5L12 12.5 3.5 8 12 3.5Zm-7.5 9 7.5 4 7.5-4",
        sparkle:     "M12 4v6M12 14v6M4 12h6M14 12h6M6.8 6.8l3 3M14.2 14.2l3 3M17.2 6.8l-3 3M9.8 14.2l-3 3",
        clock:       "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM12 7.5V12l3 2",
        history:     "M3.5 12a8.5 8.5 0 1 0 2.6-6.1M3.5 5v4h4M12 8v4.4l3 1.8",
        wave:        "M4 12h2l1.6-4.5L10 16l2.2-9L14.5 12H20",
        zap:         "M13.5 3 5.5 13.5h5L10 21l8-10.5h-5L13.5 3Z",
        copy:        "M8.5 8.5h11v11h-11Z M15.5 8.5v-2a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2",
        external:    "M14 4.5h5.5V10M19.5 4.5 11 13M18 14v4.5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4.5",
        plus:        "M12 5v14M5 12h14",
        minus:       "M5 12h14",
        refresh:     "M20 11a8 8 0 0 0-13.7-5.2L3.5 8.5M4 13a8 8 0 0 0 13.7 5.2l2.8-2.7M3.5 4.5v4h4M20.5 19.5v-4h-4",
        filter:      "M4 6h16l-6 7v5l-4 2v-7L4 6Z",
        eye:         "M2.5 12S6 6 12 6s9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Zm9.5-2.6a2.6 2.6 0 1 0 0 5.2 2.6 2.6 0 0 0 0-5.2Z",
        save:        "M5 5h11l3 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2ZM8 5v5h6V5M8 21v-6h8v6",
        keyboard:    "M3 6.5h18v11H3Z M6.5 10h.01M10 10h.01M13.5 10h.01M17 10h.01M7.5 13.5h9",
        arrow:       "M5 12h13M13 7l5 5-5 5",
        enter:       "M19 5v7a3 3 0 0 1-3 3H6M9.5 11.5 6 15l3.5 3.5",
        more:        "M6 12h.01M12 12h.01M18 12h.01",
        scissors:    "M6.5 4a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5Zm0 11a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5ZM8.7 8.3 20 18M8.7 15.7 20 6",
        bookmark:    "M6.5 4.5h11v15l-5.5-3.6L6.5 19.5v-15Z",
        gauges:      "M4 18a8 8 0 1 1 16 0M12 18l3.5-5.5M12 16.6a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8Z",
        undo:        "M4 9.5h10.5a5 5 0 0 1 0 10H8M7.5 5.5 3.5 9.5l4 4",
        split:       "M12 3.5v17M8 8 4.5 12 8 16M16 8l3.5 4-3.5 4",
        tune:        "M4 7h10M18 7h2M4 12h4M12 12h8M4 17h12M20 17h0M16 5a2 2 0 1 0 0 4 2 2 0 0 0 0-4Zm-6 3a2 2 0 1 0 0 4 2 2 0 0 0 0-4Zm8 5a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z"
    })

    function path(iconName) {
        return root._paths[iconName] !== undefined ? root._paths[iconName] : ""
    }

    Shape {
        width: 24
        height: 24
        scale: root._scale
        transformOrigin: Item.TopLeft
        visible: root._d !== ""

        ShapePath {
            strokeColor: root.color
            strokeWidth: root.strokeWidth / Math.max(root._scale, 0.0001)
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: root._d }
        }
    }
}
