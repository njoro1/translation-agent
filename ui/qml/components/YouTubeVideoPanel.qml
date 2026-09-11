import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."

// YouTube video download panel: inspect available codecs (AV1 / VP9 / H.264) and
// resolutions for the entered URL, pick a codec + resolution, see the resulting
// file size, and download the video with live progress and cancel.
//
// Subtitle downloading lives in YouTubeSubtitlePanel so the two run
// independently (separate busy flags, status text and cancel). Only shown in
// YouTube mode. Embedded into the Run page's Source card.
ColumnLayout {
    id: root

    readonly property bool hasInfo: appBridge.youtubeHasInfo
    readonly property var selectedOpt: appBridge.youtubeSelectedOption
    readonly property bool hasSelection: !!(selectedOpt && selectedOpt.format_selector)

    spacing: Theme.sm

    function humanSize(bytes) {
        if (!bytes || bytes <= 0)
            return "unknown until download (video + audio are merged)"
        var units = ["B", "KB", "MB", "GB", "TB"]
        var n = bytes
        var i = 0
        while (n >= 1024 && i < units.length - 1) {
            n /= 1024
            i++
        }
        return (i === 0 ? n.toFixed(0) : n.toFixed(1)) + " " + units[i]
    }

    // --- Inspect ---------------------------------------------------------
    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.sm

        AppButton {
            text: appBridge.youtubeInfoLoading ? "Inspecting…" : "Inspect formats"
            small: true
            iconName: "search"
            enabled: !appBridge.youtubeInfoLoading && appBridge.url.trim() !== ""
            onClicked: appBridge.fetchYouTubeInfo()
        }

        Label {
            Layout.fillWidth: true
            visible: appBridge.youtubeInfoLoading
            text: "Querying yt-dlp for available streams…"
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
        }
    }

    Label {
        Layout.fillWidth: true
        visible: appBridge.youtubeInfoError !== ""
        text: appBridge.youtubeInfoError
        color: Theme.error
        font.pixelSize: Theme.fontSmall
        wrapMode: Text.WordWrap
    }

    // --- Inspected video title -------------------------------------------
    Label {
        Layout.fillWidth: true
        visible: root.hasInfo && appBridge.youtubeTitle !== ""
        text: appBridge.youtubeTitle
        color: Theme.text
        font.pixelSize: Theme.fontBody
        font.bold: true
        wrapMode: Text.WordWrap
    }

    // --- Codec availability ---------------------------------------------
    RowLayout {
        visible: root.hasInfo
        Layout.fillWidth: true
        spacing: Theme.xs

        Label {
            text: "Codecs"
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
        }

        Repeater {
            id: codecChips
            property var chips: [
                { label: "AV1", on: appBridge.youtubeHasAv1 },
                { label: "VP9", on: appBridge.youtubeHasVp9 },
                { label: "H.264", on: appBridge.youtubeHasH264 }
            ]
            model: codecChips.chips

            delegate: Chip {
                required property var modelData
                text: modelData.label + (modelData.on ? " ✓" : " —")
                tone: modelData.on ? "acc" : ""
                mono: false
            }
        }
    }

    // --- Available formats (inspection result) ----------------------------
    Label {
        visible: root.hasInfo
        text: "Available formats (" + appBridge.youtubeFormatRows.length + ")"
        color: Theme.textMuted
        font.pixelSize: Theme.fontSmall
    }

    ScrollView {
        id: formatsScroll
        visible: root.hasInfo
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(formatsGrid.implicitHeight + 12, 240)
        clip: true

        background: Rectangle {
            color: Theme.inset
            radius: Theme.radiusSm
            border.color: Theme.borderSoft
            border.width: 1
        }

        ColumnLayout {
            id: formatsGrid
            width: formatsScroll.availableWidth
            spacing: 0

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 6
                Layout.bottomMargin: 2
                Layout.leftMargin: 10
                Layout.rightMargin: 10
                spacing: Theme.sm

                Label { Layout.preferredWidth: 56; text: "RES"; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                Label { Layout.preferredWidth: 72; text: "CODEC"; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                Label { Layout.fillWidth: true; text: "FORMAT"; color: Theme.textMuted; font.pixelSize: 10; font.bold: true }
                Label { Layout.preferredWidth: 80; text: "SIZE"; color: Theme.textMuted; font.pixelSize: 10; font.bold: true; horizontalAlignment: Text.AlignRight }
            }

            Repeater {
                model: appBridge.youtubeFormatRows

                delegate: Rectangle {
                    id: formatRow
                    required property var modelData

                    Layout.fillWidth: true
                    Layout.leftMargin: 4
                    Layout.rightMargin: 4
                    implicitHeight: 26
                    radius: Theme.radiusXs
                    color: modelData.selected ? Theme.accentSoft
                                              : (rowHover.hovered ? Theme.surface : "transparent")

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 6
                        anchors.rightMargin: 6
                        spacing: Theme.sm

                        Label {
                            Layout.preferredWidth: 56
                            text: formatRow.modelData.resLabel
                            color: Theme.text
                            font.pixelSize: Theme.fontSmall
                            font.family: Theme.monoFont
                        }
                        Label {
                            Layout.preferredWidth: 72
                            text: formatRow.modelData.codecLabel
                            color: Theme.text
                            font.pixelSize: Theme.fontSmall
                        }
                        Label {
                            Layout.fillWidth: true
                            text: formatRow.modelData.formatText
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSmall
                            elide: Text.ElideRight
                        }
                        Label {
                            Layout.preferredWidth: 80
                            text: formatRow.modelData.sizeText
                            color: Theme.textMuted
                            font.pixelSize: Theme.fontSmall
                            horizontalAlignment: Text.AlignRight
                        }
                    }

                    MouseArea {
                        id: rowHover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (formatRow.modelData.isBest) {
                                appBridge.youtubeSelectedCodec = "best"
                                appBridge.youtubeSelectedResolution = "best"
                            } else {
                                appBridge.youtubeSelectedCodec = String(formatRow.modelData.codec)
                                appBridge.youtubeSelectedResolution = String(formatRow.modelData.resolution)
                            }
                        }
                    }

                    ToolTip.visible: rowHover.containsMouse
                    ToolTip.delay: 400
                    ToolTip.text: formatRow.modelData.isBest
                        ? "Let yt-dlp pick the best available stream (any codec)."
                        : (formatRow.modelData.merge
                           ? "Separate video + audio streams, merged with ffmpeg. The size shows up during download. Click to select."
                           : "Single file containing video and audio. Click to select.")
                }
            }
        }
    }

    // --- Codec + resolution pickers --------------------------------------
    RowLayout {
        visible: root.hasInfo
        Layout.fillWidth: true
        spacing: Theme.sm

        Label { text: "Codec"; Layout.preferredWidth: 52; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
        CompactComboBox {
            id: codecCombo
            objectName: "youtubeCodecCombo"
            Layout.fillWidth: true
            model: appBridge.youtubeCodecs
            textRole: "label"
            valueRole: "id"
            label: "Video codec"
            // indexOfValue() keeps the picker in sync without hand-rolled string
            // coercion loops (a "720" vs 720 mismatch used to make the picker
            // snap back to "Best" and discard the pick).
            currentIndex: Math.max(0, indexOfValue(appBridge.youtubeSelectedCodec))
            onActivated: {
                var items = appBridge.youtubeCodecs
                if (currentIndex >= 0 && currentIndex < items.length)
                    appBridge.youtubeSelectedCodec = String(items[currentIndex].id)
            }
        }
    }

    RowLayout {
        visible: root.hasInfo
        Layout.fillWidth: true
        spacing: Theme.sm

        Label { text: "Res."; Layout.preferredWidth: 52; color: Theme.textMuted; font.pixelSize: Theme.fontSmall }
        CompactComboBox {
            id: resCombo
            objectName: "youtubeResolutionCombo"
            Layout.fillWidth: true
            model: appBridge.youtubeResolutions
            textRole: "label"
            valueRole: "value"
            label: "Video resolution"
            // The model's values and the stored selection are both strings
            // ("720" / "best"), so indexOfValue() matches exactly.
            currentIndex: Math.max(0, indexOfValue(appBridge.youtubeSelectedResolution))
            onActivated: {
                var items = appBridge.youtubeResolutions
                if (currentIndex >= 0 && currentIndex < items.length)
                    appBridge.youtubeSelectedResolution = String(items[currentIndex].value)
            }
        }
    }

    // --- Selected format summary (with file size) ------------------------
    Label {
        objectName: "youtubeSelectionLabel"
        Layout.fillWidth: true
        visible: root.hasInfo
        text: root.hasSelection
              ? "Selected: " + appBridge.youtubeSelectedFormatLabel
              : (appBridge.youtubeSelectionError !== ""
                 ? appBridge.youtubeSelectionError
                 : "No matching stream for this codec/resolution.")
        color: root.hasSelection ? Theme.text : Theme.warning
        font.pixelSize: Theme.fontSmall
        wrapMode: Text.WordWrap
    }

    Label {
        Layout.fillWidth: true
        visible: root.hasSelection
        text: "Estimated size: " + root.humanSize(appBridge.youtubeSelectedFileSize)
        color: Theme.textMuted
        font.pixelSize: Theme.fontSmall
    }

    Label {
        Layout.fillWidth: true
        visible: !root.hasInfo && !appBridge.youtubeInfoLoading
                 && appBridge.youtubeInfoError === "" && appBridge.url.trim() !== ""
        text: "Inspect the formats above to choose a codec and resolution before downloading."
        color: Theme.textMuted
        font.pixelSize: Theme.fontSmall
        wrapMode: Text.WordWrap
    }

    // --- Download actions -----------------------------------------------
    RowLayout {
        visible: root.hasInfo
        Layout.fillWidth: true
        spacing: Theme.sm

        AppButton {
            text: appBridge.youtubeVideoDownloading ? "Downloading…" : "Download video"
            small: true
            iconName: "download"
            enabled: !appBridge.youtubeVideoDownloading && root.hasSelection
            onClicked: appBridge.downloadYouTubeVideo()
        }

        AppButton {
            visible: appBridge.youtubeVideoDownloading
            text: "Cancel"
            small: true
            variant: "danger"
            onClicked: appBridge.cancelYouTubeVideoDownload()
        }

        Item { Layout.fillWidth: true }

        Label {
            visible: appBridge.youtubeVideoDownloading || appBridge.youtubeVideoProgress > 0
            text: appBridge.youtubeVideoProgress + "%"
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
            font.family: Theme.monoFont
        }
    }

    Rectangle {
        Layout.fillWidth: true
        visible: appBridge.youtubeVideoDownloading || appBridge.youtubeVideoProgress > 0
        implicitHeight: 6
        radius: 3
        color: Theme.surfaceRaised
        clip: true

        Rectangle {
            width: parent.width * Math.max(0, Math.min(1, appBridge.youtubeVideoProgress / 100))
            height: parent.height
            radius: 3
            color: Theme.accent
        }
    }

    // --- Save-to folder ---------------------------------------------------
    RowLayout {
        visible: root.hasInfo || appBridge.youtubeDownloadDir !== ""
        Layout.fillWidth: true
        spacing: Theme.sm

        Label {
            Layout.fillWidth: true
            text: "Saving to: " + appBridge.youtubeDownloadDir
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
            elide: Text.ElideMiddle
        }

        AppButton {
            text: "Change"
            small: true
            variant: "ghost"
            iconName: "folder"
            onClicked: downloadDirDialog.open()
        }
    }

    FolderDialog {
        id: downloadDirDialog
        title: "Choose the YouTube download folder"
        onAccepted: appBridge.setYouTubeDownloadDir(selectedFolder)
    }

    // --- Recovery notice --------------------------------------------------
    // A recoverable hiccup (e.g. a stale partial download that had to be
    // restarted) is promoted here so it is not lost in the raw log.
    Rectangle {
        Layout.fillWidth: true
        visible: appBridge.youtubeVideoNotice !== ""
        radius: Theme.radiusSm
        color: Theme.warningTint
        border.color: Theme.toneBorder("warn")
        border.width: 1
        implicitHeight: noticeLabel.implicitHeight + 2 * Theme.sm

        Label {
            id: noticeLabel
            anchors.fill: parent
            anchors.margins: Theme.sm
            text: appBridge.youtubeVideoNotice
            color: Theme.warning
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
            verticalAlignment: Text.AlignVCenter
        }
    }

    // --- Download progress / result ---------------------------------------
    Label {
        Layout.fillWidth: true
        visible: appBridge.youtubeVideoStatus !== ""
        text: appBridge.youtubeVideoStatus
        color: Theme.text
        font.pixelSize: Theme.fontSmall
        wrapMode: Text.WordWrap
        maximumLineCount: 8
        elide: Text.ElideRight
    }

    AppButton {
        visible: appBridge.youtubeDownloadedVideo !== ""
        text: "Open video folder"
        small: true
        variant: "ghost"
        iconName: "folder"
        onClicked: appBridge.openFolderForPath(appBridge.youtubeDownloadedVideo)
    }
}
