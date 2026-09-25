import QtQuick
import QtQuick.Controls
import ".."

// Binding-safe dropdown for a value that lives in the configuration store
// (`appBridge`).
//
// WHY THIS EXISTS — read before "simplifying" it back to `currentIndex: { … }`
//
// The obvious form is:
//
//     CompactComboBox {
//         currentIndex: { …appBridge.someValue… }   // looks reactive
//         onActivated: appBridge.someValue = currentValue
//     }
//
// That is a *declarative binding* on `currentIndex`. `ComboBox` assigns
// `currentIndex` internally when the user activates an item, and that internal
// assignment destroys the binding. From the second interaction onward the
// widget no longer mirrors the store, so a second editor for the same concept
// silently disagrees with it. Every "two widgets, one concept, different
// values" report in the UI review traces back to this.
//
// This wrapper never binds `currentIndex`. It reads the store through a
// function (`readValue`) and writes through a function (`writeValue`), then
// re-applies the index imperatively whenever the store notifies. An imperative
// assignment cannot be destroyed, so the mirror survives user interaction.
//
// Usage:
//
//     BoundComboBox {
//         model: ["off", "light", "standard", "deep"]
//         readValue: function() { return appBridge.contextMode }
//         writeValue: function(v) { appBridge.contextMode = v }
//     }
CompactComboBox {
    id: root

    // Store accessors. Functions, not values: a bound value would be destroyed
    // by the same assignment that breaks `currentIndex`.
    property var readValue: function() { return "" }
    property var writeValue: function(value) {}

    // Optional guard: skip the re-sync while this control owns focus, so a
    // background notify never fights what the user is doing.
    property bool skipSyncWhileFocused: false

    // What to show when the store holds a value the model does not contain.
    // `false` leaves the control on `-1` ("nothing selected"); `true` falls back
    // to the first entry. The download-format pickers need the fallback: an
    // empty or stale selection must read "Best", not a blank box.
    property bool selectFirstWhenMissing: false

    // NOTE: `ComboBox.currentValue` is a FINAL property in Qt 6 and cannot be
    // overridden, so the lookup is a plain function.
    function valueAt(i) {
        if (i < 0 || i >= root.model.length)
            return ""
        return root.valueRole ? root.model[i][root.valueRole] : root.model[i]
    }

    function applyStoreValue() {
        if (root.skipSyncWhileFocused && root.activeFocus)
            return
        // Compare as strings on both sides. A model that holds `720` (number)
        // against a store that holds `"720"` (string) used to miss the match,
        // snap back to the first entry and silently discard the user's pick.
        const want = String(root.readValue())
        let idx = -1
        for (let i = 0; i < root.model.length; i++) {
            const v = root.valueRole ? root.model[i][root.valueRole] : root.model[i]
            if (String(v) === want) { idx = i; break }
        }
        if (idx < 0 && root.selectFirstWhenMissing && root.model.length > 0)
            idx = 0
        if (root.currentIndex !== idx)
            root.currentIndex = idx
    }

    Component.onCompleted: applyStoreValue()

    // The model itself can arrive late (the YouTube format list only exists
    // after Inspect), so re-apply when it changes too.
    onModelChanged: applyStoreValue()

    // One `Connections` block covers every store notify signal, because each
    // handler does the same thing. `formChanged` is emitted by
    // `AppBridge._notify_form_changed()` on every field write, so it alone
    // catches most edits; the others are listed so a signal-only change (e.g.
    // a mode switch) also re-syncs.
    //
    // `youtubeInfoChanged` is not redundant: the YouTube codec/resolution
    // properties notify it *instead of* `formChanged`, so without this line the
    // two format pickers would only ever re-sync on their own activation.
    Connections {
        target: appBridge
        function onFormChanged() { root.applyStoreValue() }
        function onPipelineModeChanged() { root.applyStoreValue() }
        function onThemeChanged() { root.applyStoreValue() }
        function onResultReadyChanged() { root.applyStoreValue() }
        function onYoutubeInfoChanged() { root.applyStoreValue() }
    }

    onActivated: (index) => {
        root.writeValue(root.valueAt(index))
        // Re-read immediately: the store may normalise the value (e.g. an
        // unknown id falls back to a default), and the widget must show what
        // is actually in effect rather than what was clicked.
        root.applyStoreValue()
    }
}
