import QtQuick
import QtQuick.Controls
import ".."

// Content preset selector (auto / drama / anime / music / documentary /
// variety / lecture). Tunes ASR, preprocessing, context and prompt style.
CompactComboBox {
    id: root

    model: [
        { id: "auto", label: "Auto · detect" },
        { id: "drama", label: "Drama" },
        { id: "anime", label: "Anime" },
        { id: "music", label: "Music" },
        { id: "documentary", label: "Documentary" },
        { id: "variety", label: "Variety" },
        { id: "lecture", label: "Lecture" }
    ]
    textRole: "label"
    valueRole: "id"
    label: "Content preset"
    currentIndex: {
        for (let i = 0; i < model.length; i++) {
            if (model[i].id === appBridge.contentPreset) return i
        }
        return 0
    }
    onActivated: appBridge.contentPreset = currentValue

    ToolTip.visible: hovered
    ToolTip.delay: 500
    ToolTip.text: "Content preset tunes ASR, preprocessing, context and prompt style."
}
