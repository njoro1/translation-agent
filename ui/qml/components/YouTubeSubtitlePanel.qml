import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// YouTube subtitle download panel: deliberately separate from the video
// download (YouTubeVideoPanel) so each has its own busy flag, status text and
// cancel — both can run at the same time. Only shown in YouTube mode.
SectionPanel {
    id: root

    title: "Download the English subtitle (source)"
    visible: window.isYouTubeMode
    Layout.fillWidth: true

    ColumnLayout {
        width: parent.width
        spacing: Theme.sm

        // Data-flow sentence (U-13): make it explicit where this subtitle goes.
        Label {
            Layout.fillWidth: true
            text: "This English subtitle becomes the SOURCE text. Once downloaded, " +
                  "go to the Translate section — the app translates it into your target language."
            color: Theme.text
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
        }

        Label {
            Layout.fillWidth: true
            visible: appBridge.youtubeHasInfo
            text: appBridge.youtubeHasEnglishSubtitle
                  ? "An English subtitle track is available for this video."
                  : "No English subtitle track is available for this video."
            color: appBridge.youtubeHasEnglishSubtitle ? Theme.text : Theme.textMuted
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
        }

        Label {
            Layout.fillWidth: true
            visible: !appBridge.youtubeHasInfo
            text: "Inspect the video above to check for an English subtitle track."
            color: Theme.textMuted
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.sm

            Button {
                text: appBridge.youtubeSubDownloading ? "Downloading…" : "Download English subtitle"
                enabled: !appBridge.youtubeSubDownloading
                         && appBridge.youtubeHasEnglishSubtitle
                onClicked: appBridge.downloadYouTubeSubtitle()

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
                visible: appBridge.youtubeSubDownloading
                text: "Cancel"
                onClicked: appBridge.cancelYouTubeSubtitleDownload()

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

        Label {
            Layout.fillWidth: true
            visible: appBridge.youtubeSubStatus !== ""
            text: appBridge.youtubeSubStatus
            color: Theme.text
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
            maximumLineCount: 12
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
