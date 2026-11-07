import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "." as App

App.Pill {
    id: pill

    property string doneText: ""
    property bool failed: false
    readonly property bool updating: svwr.running && svwr.action === "update"

    signal detailsRequested()

    shown: svwr.updateAvailable || updating || doneText !== "" || failed

    Connections {
        target: svwr

        function onFinished(ok) {
            if (svwr.action !== "update")
                return
            pill.failed = !ok
            if (ok) {
                pill.doneText = "Smart Video Wallpaper Reborn updated to " + svwr.version
                doneTimer.restart()
            }
        }
    }

    Timer {
        id: doneTimer
        interval: 3000
        onTriggered: pill.doneText = ""
    }

    Rectangle {
        implicitWidth: 8
        implicitHeight: 8
        radius: 4
        color: pill.failed ? Kirigami.Theme.negativeTextColor
            : pill.doneText !== "" ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.neutralTextColor
    }

    QQC2.Label {
        Layout.maximumWidth: 360
        elide: Text.ElideRight
        text: pill.doneText !== "" ? pill.doneText
            : pill.failed ? "Smart Video Wallpaper Reborn update failed"
            : pill.updating ? (svwr.stage || "Updating…")
            : "Smart Video Wallpaper Reborn " + svwr.latest.replace(/^v/, "") + " is available"
    }

    QQC2.ProgressBar {
        visible: pill.updating
        Layout.preferredWidth: 90
        from: 0
        to: 1
        value: svwr.progress
    }

    QQC2.Button {
        visible: !pill.updating && pill.doneText === "" && !pill.failed
        text: "Update"
        icon.name: "update-none"
        highlighted: true
        onClicked: svwr.update()
    }

    QQC2.Button {
        visible: pill.failed
        text: "Details"
        onClicked: {
            pill.failed = false
            pill.detailsRequested()
        }
    }
}
