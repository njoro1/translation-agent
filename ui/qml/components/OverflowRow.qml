import QtQuick
import ".."

// A row that wraps instead of clipping (UI review D4).
//
// `RowLayout` has no wrap: when the seven Quality metrics cannot fit the card,
// it shrinks every cell until `elide` chops the labels mid-word — "MAX LINE
// CH…", "LEAKAGE · EMPTY · M…". The card stayed the same height and the
// information was lost. `Flow` wraps to a second line instead, so the card
// grows by one row and every label stays whole.
//
// The caller owns the cell geometry: bind each child's `width` to
// `cellWidth` (Flow does not resize its children). `cellWidth` is derived from
// `minCellWidth`, so the row always uses as many columns as fit and never
// produces a cell narrower than the minimum.
//
//     OverflowRow {
//         id: metrics
//         Repeater {
//             model: appBridge.qualityTiles
//             delegate: MetricChip { width: metrics.cellWidth; ... }
//         }
//     }
Item {
    id: root

    default property alias content: flow.data

    property int spacing: Theme.sm
    // The narrowest a cell may get before the row wraps to a new line.
    property int minCellWidth: 148
    // 0 = as many columns as fit.
    property int maxColumns: 0

    readonly property int _fitting: Math.max(
        1, Math.floor((width + spacing) / (minCellWidth + spacing)))
    readonly property int columns: maxColumns > 0
        ? Math.min(maxColumns, _fitting) : _fitting
    readonly property real cellWidth: Math.max(
        0, (width - spacing * (columns - 1)) / columns)

    // `implicitWidth` is deliberately NOT derived from the Flow.
    //
    // The children's widths come from `cellWidth`, which comes from `width`. If
    // the item also published an `implicitWidth` derived from those children,
    // a parent Layout would compute the assigned width from a preferred width
    // that is itself a function of the assigned width. That cycle does not
    // settle, and `QGuiApplication.processEvents()` never returns — the window
    // simply freezes when the page is first laid out.
    implicitHeight: flow.implicitHeight

    Flow {
        id: flow
        width: root.width
        spacing: root.spacing
    }
}
