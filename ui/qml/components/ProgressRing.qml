import QtQuick
import ".."

// Circular progress ring. ``value`` is 0..1.
Canvas {
    id: root

    property real value: 0
    property real thickness: 8
    property color trackColor: Theme.surfaceRaised
    property color valueColor: Theme.accent

    antialiasing: true

    onValueChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onTrackColorChanged: requestPaint()
    onValueColorChanged: requestPaint()
    onThicknessChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        var c = width / 2
        var r = Math.max(1, Math.min(width, height) / 2 - thickness / 2)
        ctx.lineWidth = thickness
        ctx.lineCap = "round"

        ctx.strokeStyle = trackColor
        ctx.beginPath()
        ctx.arc(c, c, r, 0, 2 * Math.PI)
        ctx.stroke()

        var v = Math.max(0, Math.min(1, root.value))
        if (v > 0.001) {
            ctx.strokeStyle = valueColor
            ctx.beginPath()
            ctx.arc(c, c, r, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * v)
            ctx.stroke()
        }
    }
}
