import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import "." as App

App.Pill {
    shown: appUpdate.available || appUpdate.running

    QQC2.Label {
        visible: appUpdate.running
        text: "Updating to " + appUpdate.version + "… " + Math.round(appUpdate.progress * 100) + "%"
    }

    QQC2.ProgressBar {
        visible: appUpdate.running
        Layout.preferredWidth: 90
        from: 0
        to: 1
        value: appUpdate.progress
    }

    QQC2.Button {
        visible: !appUpdate.running
        text: "Update to " + appUpdate.version
        icon.name: "update-none"
        highlighted: true
        onClicked: appUpdate.install()
    }
}
