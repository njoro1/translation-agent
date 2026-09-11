import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// Shared console widget. Used by the Run screen's "Live log" card and by the
// Log page's full-height console.
//
// Lines are parsed once per log change into {stamp, body, tone} objects so the
// delegate stays a plain binding, and a ListView keeps a 5000-line log cheap.
// Tone drives colour only as a reinforcement: the text itself carries the
// `[warn]` / `[error]` prefix, so nothing depends on colour alone.
Item {
    id: root

    property string query: ""
    // "" (everything) | "info" (unclassified) | "warn" | "err"
    property string toneFilter: ""
    property bool follow: true
    property string emptyText: "No output yet."

    readonly property var _parsed: {
        const raw = appBridge.logText ? String(appBridge.logText).split("\n") : []
        const q = root.query.trim().toLowerCase()
        const out = []
        for (let i = 0; i < raw.length; i++) {
            const line = raw[i]
            if (line === "" && i === raw.length - 1)
                continue
            if (q !== "" && line.toLowerCase().indexOf(q) < 0)
                continue
            let stamp = ""
            let body = line
            const m = /^(\d{2}:\d{2}:\d{2})\s?(.*)$/.exec(line)
            if (m) {
                stamp = m[1]
                body = m[2]
            }
            out.push({ stamp: stamp, body: body, tone: root._tone(body) })
        }
        return out
    }

    readonly property var lines: {
        if (root.toneFilter === "")
            return root._parsed
        const want = root.toneFilter
        const out = []
        for (let i = 0; i < root._parsed.length; i++) {
            const t = root._parsed[i].tone
            if (want === "info" && t === "")
                out.push(root._parsed[i])
            else if (want !== "info" && t === want)
                out.push(root._parsed[i])
        }
        return out
    }

    readonly property var counts: {
        let info = 0
        let warn = 0
        let err = 0
        for (let i = 0; i < root._parsed.length; i++) {
            const t = root._parsed[i].tone
            if (t === "warn")
                warn++
            else if (t === "err")
                err++
            else
                info++
        }
        return { all: root._parsed.length, info: info, warn: warn, err: err }
    }

    readonly property int lineCount: root.lines.length

    function _tone(body) {
        const s = body.toLowerCase()
        if (s.indexOf("[error]") >= 0 || s.indexOf("[err]") >= 0
                || s.indexOf("traceback") >= 0 || s.indexOf("error:") >= 0)
            return "err"
        if (s.indexOf("[warn") >= 0 || s.indexOf("warning") >= 0)
            return "warn"
        if (s.indexOf("[ok]") >= 0 || s.indexOf("wrote ") >= 0 || s.indexOf("[done]") >= 0)
            return "ok"
        if (body.indexOf("$ ") === 0 || body.indexOf("[info]") >= 0 || body.indexOf("[env]") >= 0)
            return "info"
        return ""
    }

    function _color(tone) {
        if (tone === "err") return Theme.error
        if (tone === "warn") return Theme.warning
        if (tone === "ok") return Theme.success
        return Theme.textDim
    }

    function scrollToBottom() {
        view.positionViewAtEnd()
    }

    implicitHeight: 160

    onLinesChanged: if (root.follow) Qt.callLater(root.scrollToBottom)

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusSm
        color: Theme.inset
        border.color: Theme.borderSoft
        border.width: 1
        clip: true

        ListView {
            id: view
            anchors.fill: parent
            anchors.margins: 9
            model: root.lines
            spacing: 1
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Row {
                id: line
                required property var modelData
                required property int index

                width: view.width
                spacing: 9

                Label {
                    visible: line.modelData.stamp !== ""
                    width: 56
                    text: line.modelData.stamp
                    color: Theme.textMuted
                    font.family: Theme.monoFont
                    font.pixelSize: Theme.fontTiny
                }

                Text {
                    width: view.width - (line.modelData.stamp !== "" ? 65 : 0)
                    text: line.modelData.body
                    color: root._color(line.modelData.tone)
                    font.family: Theme.monoFont
                    font.pixelSize: Theme.fontTiny
                    wrapMode: Text.WrapAnywhere
                    textFormat: Text.PlainText
                }
            }

            Text {
                anchors.centerIn: parent
                width: parent.width - 24
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                visible: view.count === 0
                text: root.emptyText
                color: Theme.textMuted
                font.pixelSize: Theme.fontTiny
                font.family: Theme.monoFont
            }
        }
    }
}
