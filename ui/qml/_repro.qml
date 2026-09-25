import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    width: 1180; height: 200; visible: true
    RowLayout {
        anchors.fill: parent
        spacing: 16
        ColumnLayout {
            Layout.preferredWidth: 288
            Layout.minimumWidth: 240
            Layout.maximumWidth: 288
            Layout.fillHeight: true
            Rectangle { Layout.fillWidth: true; Layout.fillHeight: true; color: "red" }
        }
        Rectangle { Layout.fillWidth: true; Layout.fillHeight: true; color: "blue" }
    }
}
