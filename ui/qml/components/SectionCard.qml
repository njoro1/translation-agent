import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property string title: ""
    property string subtitle: ""
    default property alias contentData: contentColumn.data

    color: "#111827"
    radius: 18
    border.color: "#27272a"
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 14

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4

            Label {
                text: root.title
                color: "#f4f4f5"
                font.pixelSize: 16
                font.bold: true
            }

            Label {
                visible: text.length > 0
                text: root.subtitle
                color: "#94a3b8"
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        ColumnLayout {
            id: contentColumn
            Layout.fillWidth: true
            spacing: 12
        }
    }
}
