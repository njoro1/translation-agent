import QtQuick
import QtQuick.Controls
import ".."

// Binding-safe editable field for a value that lives in the configuration
// store (`appBridge`).
//
// WHY THIS EXISTS
//
//     CompactComboBox {
//         editable: true
//         editText: appBridge.someValue          // looks reactive
//         onAccepted: appBridge.someValue = editText
//     }
//
// `editText` is written by the internal `TextField` on every keystroke, which
// destroys the declarative binding — so the field stops mirroring the store
// after the first character the user types, and a second editor for the same
// concept drifts out of sync. Same failure class as `BoundComboBox`.
//
// This wrapper reads through `readValue` and writes through `writeValue`, and
// never relies on a binding over `editText`.
//
// Usage:
//
//     BoundField {
//         model: ["auto", "ja", "zh", "en"]
//         readValue: function() { return appBridge.asrLanguage }
//         writeValue: function(v) { appBridge.asrLanguage = v }
//     }
CompactComboBox {
    id: root

    editable: true

    property var readValue: function() { return "" }
    property var writeValue: function(value) {}
    // Fallback applied when the store holds an empty string, so a field that
    // inherits a value never renders as a blank box.
    property string emptyFallback: ""

    function applyStoreValue() {
        // Never overwrite what the user is currently typing: a background
        // notify would otherwise yank the cursor mid-word.
        if (root.activeFocus)
            return
        const want = root.readValue()
        const shown = want === "" ? root.emptyFallback : want
        if (root.editText !== shown)
            root.editText = shown
    }

    function commit() {
        root.writeValue(root.editText.trim())
        root.applyStoreValue()
    }

    Component.onCompleted: applyStoreValue()

    Connections {
        target: appBridge
        function onFormChanged() { root.applyStoreValue() }
        function onPipelineModeChanged() { root.applyStoreValue() }
        function onThemeChanged() { root.applyStoreValue() }
    }

    onAccepted: root.commit()
    onActivated: root.commit()
    // Commit when focus leaves, so a typed value is not lost if the user never
    // presses Enter. `ComboBox` has no `editingFinished` (that is a TextField
    // signal), so focus loss is the hook.
    onActiveFocusChanged: {
        if (!root.activeFocus)
            root.commit()
    }
}
