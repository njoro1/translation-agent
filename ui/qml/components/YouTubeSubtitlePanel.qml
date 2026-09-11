import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

// YouTube subtitle download panel: deliberately separate from the video download
// (YouTubeVideoPanel) so each has its own busy flag, status text and cancel —
// both can run at the same time.
//
// The downloaded English subtitle becomes the SOURCE text of the translation,
// which is stated explicitly so the two-step flow is obvious.
ColumnLayout {
    id: root

    spacing: Theme.sm

    Label {
        Layout.fillWidth: true
        text: "This English subtitle becomes the SOURCE text. Once downloaded, " +
              "run the translation — the pipeline translates it into English subtitles."
        color: Theme.textDim
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
        text: "Inspect the formats above to check for an English subtitle track."
        color: Theme.textMuted
        font.pixelSize: Theme.fontSmall
        wrapMode: Text.WordWrap
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: Theme.sm

        AppButton {
            text: appBridge.youtubeSubDownloading ? "Downloading…" : "Download English subtitle"
            small: true
            iconName: "download"
            enabled: !appBridge.youtubeSubDownloading && appBridge.youtubeHasEnglishSubtitle
            onClicked: appBridge.downloadYouTubeSubtitle()
        }

        AppButton {
            visible: appBridge.youtubeSubDownloading
            text: "Cancel"
            small: true
            variant: "danger"
            onClicked: appBridge.cancelYouTubeSubtitleDownload()
        }

        Item { Layout.fillWidth: true }
    }

    Label {
        Layout.fillWidth: true
        visible: appBridge.youtubeSubStatus !== ""
        text: appBridge.youtubeSubStatus
        color: Theme.text
        font.pixelSize: Theme.fontSmall
        wrapMode: Text.WordWrap
        maximumLineCount: 8
        elide: Text.ElideRight
    }

    AppButton {
        visible: appBridge.youtubeDownloadedSubtitle !== ""
        text: "Open subtitle folder"
        small: true
        variant: "ghost"
        iconName: "folder"
        onClicked: appBridge.openFolderForPath(appBridge.youtubeDownloadedSubtitle)
    }
}
