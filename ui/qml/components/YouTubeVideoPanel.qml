import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import ".."

// YouTube video download panel: inspect available codecs (AV1 / VP9 / H.264)
// and resolutions for the entered URL, pick a codec + resolution, see the
// resulting file size, and download the video with live progress and cancel.
// Subtitle downloading lives in YouTubeSubtitlePanel so the two run
// independently. Only shown in YouTube mode.
SectionPanel {
    id: root

    readonly property bool hasInfo: appBridge.youtubeHasInfo
    readonly property var selectedOpt: appBridge.youtubeSelectedOption
    readonly property bool hasSelection: !!(selectedOpt && selectedOpt.format_selector)

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

    title: "Also download the video (optional)"
    expanded: false
    visible: window.isYouTubeMode
    Layout.fillWidth: true

    ColumnLayout {
        width: parent.width
        spacing: Theme.sm

        // --- Inspect ---------------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.sm

            Button {
                text: appBridge.youtubeInfoLoading ? "Inspecting…" : "Inspect formats"
                enabled: !appBridge.youtubeInfoLoading
                         && appBridge.url.trim() !== ""
                onClicked: appBridge.fetchYouTubeInfo()

                background: Rectangle {
                    radius: Theme.radiusSm
                    color: parent.enabled
                           ? (parent.hovered ? Theme.accentHover : Theme.accent)
                           : Theme.surfaceAlt
                }
                contentItem: Label {
                    text: parent.text
                    color: parent.enabled ? "#FFFFFF" : Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
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
            text: "\u201C" + appBridge.youtubeTitle + "\u201D"
            color: Theme.text
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
        }

        // --- Codec availability ---------------------------------------------
        RowLayout {
            visible: root.hasInfo
            Layout.fillWidth: true
            spacing: Theme.xs

            Label {
                text: "Codecs:"
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

                delegate: Rectangle {
                    id: chip
                    required property var modelData
                    radius: Theme.radiusSm
                    border.color: Theme.border
                    border.width: 1
                    color: modelData.on ? Theme.accent : Theme.surfaceAlt
                    width: chipText.implicitWidth + 16
                    height: 22

                    HoverHandler { id: chipHover }

                    Label {
                        id: chipText
                        anchors.centerIn: parent
                        text: modelData.label + (modelData.on ? " ✓" : " —")
                        color: modelData.on ? "#FFFFFF" : Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                    }
                    ToolTip.visible: chipHover.hovered
                    ToolTip.delay: 300
                    ToolTip.text: modelData.on
                            ? modelData.label + " stream available for this video"
                            : modelData.label + " not available for this video"
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
            Layout.preferredHeight: Math.min(formatsGrid.implicitHeight + 12, 280)

            background: Rectangle {
                color: Theme.surfaceAlt
                radius: Theme.radiusSm
                border.color: Theme.border
                border.width: 1
            }

            ColumnLayout {
                id: formatsGrid
                width: formatsScroll.availableWidth
                spacing: 0

                // Header row
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    Layout.bottomMargin: 2
                    Layout.leftMargin: 10
                    Layout.rightMargin: 10
                    spacing: Theme.sm

                    Label {
                        Layout.preferredWidth: 56
                        text: "RES"
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        font.bold: true
                    }
                    Label {
                        Layout.preferredWidth: 72
                        text: "CODEC"
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        font.bold: true
                    }
                    Label {
                        Layout.fillWidth: true
                        text: "FORMAT"
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        font.bold: true
                    }
                    Label {
                        Layout.preferredWidth: 80
                        text: "SIZE"
                        color: Theme.textMuted
                        font.pixelSize: Theme.fontSmall
                        font.bold: true
                        horizontalAlignment: Text.AlignRight
                    }
                }

                // One row per stream combination yt-dlp reported.
                Repeater {
                    model: appBridge.youtubeFormatRows

                    delegate: Rectangle {
                        id: formatRow
                        required property var modelData

                        Layout.fillWidth: true
                        Layout.leftMargin: 4
                        Layout.rightMargin: 4
                        implicitHeight: 26
                        radius: Theme.radiusSm
                        color: modelData.selected ? Qt.alpha(Theme.accent, 0.18)
                                                  : (rowHover.containsMouse ? Theme.surface
                                                                            : "transparent")

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
                                    appBridge.youtubeSelectedCodec =
                                            String(formatRow.modelData.codec)
                                    appBridge.youtubeSelectedResolution =
                                            String(formatRow.modelData.resolution)
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

            FieldLabel { text: "Codec"; Layout.preferredWidth: 60 }
            CompactComboBox {
                id: codecCombo
                objectName: "youtubeCodecCombo"
                Layout.fillWidth: true
                model: appBridge.youtubeCodecs
                textRole: "label"
                valueRole: "id"
                // indexOfValue() keeps the picker in sync without hand-rolled
                // string coercion loops (a "720" vs 720 mismatch used to make
                // the picker snap back to "Best" and discard the pick).
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

            FieldLabel { text: "Res."; Layout.preferredWidth: 60 }
            CompactComboBox {
                id: resCombo
                objectName: "youtubeResolutionCombo"
                Layout.fillWidth: true
                model: appBridge.youtubeResolutions
                textRole: "label"
                valueRole: "value"
                // The model's values and the stored selection are both strings
                // ("720" / "best"), so indexOfValue() matches exactly — no
                // int-vs-string coercion that can silently fail.
                currentIndex: Math.max(0, indexOfValue(appBridge.youtubeSelectedResolution))
                onActivated: {
                    var items = appBridge.youtubeResolutions
                    if (currentIndex >= 0 && currentIndex < items.length)
                        appBridge.youtubeSelectedResolution = String(items[currentIndex].value)
                }
            }
        }

        // --- Selected format summary (with file size) ------------------------
        RowLayout {
            visible: root.hasInfo
            Layout.fillWidth: true
            spacing: Theme.sm

            Label {
                objectName: "youtubeSelectionLabel"
                Layout.fillWidth: true
                text: root.hasSelection
                      ? "Selected: " + appBridge.youtubeSelectedFormatLabel
                      : (appBridge.youtubeSelectionError !== ""
                         ? appBridge.youtubeSelectionError
                         : "No matching stream for this codec/resolution.")
                color: root.hasSelection ? Theme.text : Theme.warning
                font.pixelSize: Theme.fontSmall
                wrapMode: Text.WordWrap
            }
        }

        Label {
            Layout.fillWidth: true
            visible: root.hasSelection
            text: "Estimated size: " + root.humanSize(appBridge.youtubeSelectedFileSize)
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
        }

        // --- Download actions -----------------------------------------------
        Label {
            Layout.fillWidth: true
            visible: !root.hasInfo && !appBridge.youtubeInfoLoading
                     && appBridge.youtubeInfoError === ""
                     && appBridge.url.trim() !== ""
            text: "Click \u201CInspect formats\u201D above to see the available " +
                  "codecs and resolutions before downloading."
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
        }

        RowLayout {
            visible: root.hasInfo
            Layout.fillWidth: true
            spacing: Theme.sm

            Button {
                text: appBridge.youtubeVideoDownloading ? "Downloading…" : "Download video"
                enabled: !appBridge.youtubeVideoDownloading && root.hasSelection
                onClicked: appBridge.downloadYouTubeVideo()

                background: Rectangle {
                    radius: Theme.radiusSm
                    color: parent.enabled
                           ? (parent.hovered ? Theme.accentHover : Theme.accent)
                           : Theme.surfaceAlt
                }
                contentItem: Label {
                    text: parent.text
                    color: parent.enabled ? "#FFFFFF" : Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Button {
                visible: appBridge.youtubeVideoDownloading
                text: "Cancel"
                onClicked: appBridge.cancelYouTubeVideoDownload()

                background: Rectangle {
                    radius: Theme.radiusSm
                    color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                    border.color: Theme.error
                    border.width: 1
                }
                contentItem: Label {
                    text: parent.text
                    color: Theme.error
                    font.pixelSize: Theme.fontSmall
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        // --- Live download progress ------------------------------------------
        RowLayout {
            visible: appBridge.youtubeVideoDownloading
                     || appBridge.youtubeVideoProgress > 0
            Layout.fillWidth: true
            spacing: Theme.sm

            ProgressBar {
                id: videoProgress
                Layout.fillWidth: true
                from: 0
                to: 100
                value: appBridge.youtubeVideoProgress
                indeterminate: appBridge.youtubeVideoDownloading
                               && appBridge.youtubeVideoProgress <= 0

                background: Rectangle {
                    implicitHeight: 6
                    radius: 3
                    color: Theme.surfaceAlt
                    border.color: Theme.border
                    border.width: 1
                }
                contentItem: Item {
                    implicitHeight: 6

                    Rectangle {
                        visible: !videoProgress.indeterminate
                        width: videoProgress.visualPosition * parent.width
                        height: parent.height
                        radius: 3
                        color: Theme.accent
                    }

                    Rectangle {
                        visible: videoProgress.indeterminate
                        anchors.fill: parent
                        radius: 3
                        color: Theme.accent
                        opacity: 0.4
                    }
                }
            }

            Label {
                visible: !videoProgress.indeterminate
                text: appBridge.youtubeVideoProgress + "%"
                color: Theme.textMuted
                font.pixelSize: Theme.fontSmall
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

            Button {
                text: "Change…"
                onClicked: downloadDirDialog.open()

                background: Rectangle {
                    radius: Theme.radiusSm
                    color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                    border.color: Theme.border
                    border.width: 1
                }
                contentItem: Label {
                    text: parent.text
                    color: Theme.text
                    font.pixelSize: Theme.fontSmall
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        FolderDialog {
            id: downloadDirDialog
            title: "Choose the YouTube download folder"
            onAccepted: appBridge.setYouTubeDownloadDir(selectedFolder)
        }

        // --- Recovery notice ------------------------------------------------
        // A recoverable hiccup (e.g. a stale partial download that had to be
        // restarted) is promoted here so it is not lost in the raw log below.
        Rectangle {
            Layout.fillWidth: true
            visible: appBridge.youtubeVideoNotice !== ""
            radius: Theme.radiusSm
            color: Theme.warningTint
            border.color: Theme.warning
            border.width: 1
            Layout.preferredHeight: noticeLabel.implicitHeight + 2 * Theme.sm

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

        // --- Download progress / result -------------------------------------
        Label {
            Layout.fillWidth: true
            visible: appBridge.youtubeVideoStatus !== ""
            text: appBridge.youtubeVideoStatus
            color: Theme.text
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
            maximumLineCount: 12
        }

        RowLayout {
            visible: appBridge.youtubeDownloadedVideo !== ""
            Layout.fillWidth: true
            spacing: Theme.sm

            Button {
                visible: appBridge.youtubeDownloadedVideo !== ""
                text: "Open video folder"
                onClicked: appBridge.openFolderForPath(appBridge.youtubeDownloadedVideo)

                background: Rectangle {
                    radius: Theme.radiusSm
                    color: parent.hovered ? Theme.surfaceAlt : Theme.surface
                    border.color: Theme.border
                    border.width: 1
                }
                contentItem: Label {
                    text: parent.text
                    color: Theme.text
                    font.pixelSize: Theme.fontSmall
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }
}
