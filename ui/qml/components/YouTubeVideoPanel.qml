import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// YouTube media download panel: inspect available codecs (AV1 / VP9 / H.264)
// and resolutions for the entered URL, pick a codec + resolution, see the
// resulting file size, and download the video and/or its English subtitle
// track. Only shown in YouTube mode.
SectionPanel {
    id: root

    readonly property bool hasInfo: appBridge.youtubeHasInfo
    readonly property var selectedOpt: appBridge.youtubeSelectedOption
    readonly property bool hasSelection: !!(selectedOpt && selectedOpt.format_selector)

    function humanSize(bytes) {
        if (!bytes || bytes <= 0)
            return "unknown (video + audio merge)"
        var units = ["B", "KB", "MB", "GB", "TB"]
        var n = bytes
        var i = 0
        while (n >= 1024 && i < units.length - 1) {
            n /= 1024
            i++
        }
        return (i === 0 ? n.toFixed(0) : n.toFixed(1)) + " " + units[i]
    }

    title: "YouTube Video"
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
                                            formatRow.modelData.codec
                                    appBridge.youtubeSelectedResolution =
                                            formatRow.modelData.resolution
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
                Layout.fillWidth: true
                model: appBridge.youtubeCodecs
                textRole: "label"
                currentIndex: {
                    var items = appBridge.youtubeCodecs
                    var sel = appBridge.youtubeSelectedCodec
                    for (var i = 0; i < items.length; i++)
                        if (items[i].id === sel) return i
                    return 0
                }
                onActivated: {
                    var items = appBridge.youtubeCodecs
                    if (currentIndex >= 0 && currentIndex < items.length)
                        appBridge.youtubeSelectedCodec = items[currentIndex].id
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
                Layout.fillWidth: true
                model: appBridge.youtubeResolutions
                textRole: "label"
                currentIndex: {
                    var items = appBridge.youtubeResolutions
                    var sel = appBridge.youtubeSelectedResolution
                    for (var i = 0; i < items.length; i++)
                        if (items[i].value === sel) return i
                    return items.length - 1
                }
                onActivated: {
                    var items = appBridge.youtubeResolutions
                    if (currentIndex >= 0 && currentIndex < items.length)
                        appBridge.youtubeSelectedResolution = items[currentIndex].value
                }
            }
        }

        // --- Selected format summary (with file size) ------------------------
        RowLayout {
            visible: root.hasInfo
            Layout.fillWidth: true
            spacing: Theme.sm

            Label {
                Layout.fillWidth: true
                text: root.hasSelection
                      ? "Selected: " + appBridge.youtubeSelectedFormatLabel
                      : "No matching stream for this codec/resolution."
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
        RowLayout {
            visible: root.hasInfo
            Layout.fillWidth: true
            spacing: Theme.sm

            Button {
                text: "Download video"
                enabled: !appBridge.youtubeDownloading && root.hasSelection
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
                text: "Download English subtitle"
                enabled: !appBridge.youtubeDownloading
                         && appBridge.youtubeHasEnglishSubtitle
                onClicked: appBridge.downloadYouTubeSubtitle()

                background: Rectangle {
                    radius: Theme.radiusSm
                    color: parent.enabled
                           ? (parent.hovered ? Theme.surfaceAlt : Theme.surface)
                           : Theme.surfaceAlt
                    border.color: Theme.border
                    border.width: 1
                }
                contentItem: Label {
                    text: parent.text
                    color: parent.enabled ? Theme.text : Theme.textMuted
                    font.pixelSize: Theme.fontSmall
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        Label {
            Layout.fillWidth: true
            visible: root.hasInfo && !appBridge.youtubeHasEnglishSubtitle
            text: "No English subtitle track is available for this video."
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
        }

        Label {
            Layout.fillWidth: true
            visible: root.hasInfo
            text: "Saving to: " + appBridge.youtubeDownloadDir
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
            elide: Text.ElideMiddle
        }

        // --- Download progress / result -------------------------------------
        Label {
            Layout.fillWidth: true
            visible: appBridge.youtubeDownloadStatus !== ""
            text: appBridge.youtubeDownloadStatus
            color: Theme.text
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
            maximumLineCount: 12
        }

        RowLayout {
            visible: appBridge.youtubeDownloadedVideo !== ""
                     || appBridge.youtubeDownloadedSubtitle !== ""
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

            Button {
                visible: appBridge.youtubeDownloadedSubtitle !== ""
                text: "Open subtitle folder"
                onClicked: appBridge.openFolderForPath(appBridge.youtubeDownloadedSubtitle)

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
