import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "." as App

QQC2.ScrollView {
    id: page

    readonly property string cardState: svwr.running ? "running" : svwr.error !== "" ? "error"
        : svwr.installed ? "done" : "missing"

    contentWidth: availableWidth
    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

    App.SvwrRepoPrompt {
        id: repoPrompt
    }

    ColumnLayout {
        width: page.availableWidth
        spacing: Kirigami.Units.largeSpacing

        App.SettingsParts.PageHeader {
            Layout.margins: Kirigami.Units.gridUnit
            Layout.bottomMargin: 0
            title: "Live Wallpapers"
            lead: "Browse and set animated video wallpapers on Plasma. This needs the Smart Video Wallpaper Reborn plugin."
        }

        App.SettingsParts.Group {
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.rightMargin: Kirigami.Units.gridUnit

            App.SettingsParts.Row {
                separator: false
                title: "Enable Live Wallpapers"
                subtitle: !svwr.installed ? "Install Smart Video Wallpaper Reborn first"
                    : settings.liveEnabled ? "Live sources and folder are available"
                    : "Plugin found, you can turn this on"
                leading: Kirigami.Icon {
                    source: "video-x-generic"
                    implicitWidth: Kirigami.Units.iconSizes.medium
                    implicitHeight: implicitWidth
                }

                QQC2.Switch {
                    enabled: svwr.installed && !svwr.running
                    checked: settings.liveEnabled
                    onToggled: {
                        settings.liveEnabled = checked
                        checked = Qt.binding(() => settings.liveEnabled)
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.rightMargin: Kirigami.Units.gridUnit
            implicitHeight: card.implicitHeight + Kirigami.Units.largeSpacing * 2
            radius: Kirigami.Units.cornerRadius * 2
            color: page.cardState === "done" ? Kirigami.Theme.positiveBackgroundColor
                : page.cardState === "error" ? Kirigami.Theme.negativeBackgroundColor
                : Kirigami.Theme.neutralBackgroundColor
            border.width: 1
            border.color: page.cardState === "done" ? Kirigami.Theme.positiveTextColor
                : page.cardState === "error" ? Kirigami.Theme.negativeTextColor
                : Kirigami.Theme.neutralTextColor

            Behavior on color {
                ColorAnimation { duration: Kirigami.Units.longDuration }
            }

            RowLayout {
                id: card

                anchors.fill: parent
                anchors.margins: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.largeSpacing

                Kirigami.Icon {
                    Layout.alignment: Qt.AlignTop
                    implicitWidth: Kirigami.Units.iconSizes.medium
                    implicitHeight: implicitWidth
                    source: page.cardState === "done" ? "data-success" : page.cardState === "error" ? "data-error"
                        : page.cardState === "running" ? "run-build" : "data-warning"
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    QQC2.Label {
                        Layout.fillWidth: true
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                        text: {
                            switch (page.cardState) {
                            case "running":
                                return svwr.action === "update" ? "Updating Smart Video Wallpaper Reborn"
                                    : svwr.action === "deps" ? "Installing packages"
                                    : "Installing Smart Video Wallpaper Reborn"
                            case "error":
                                return svwr.action === "deps" ? "Package install failed"
                                    : svwr.action === "update" ? "Update failed" : "Install failed"
                            case "done":
                                return "Smart Video Wallpaper Reborn " + svwr.version + " is installed"
                            }
                            return "Smart Video Wallpaper Reborn is not installed"
                        }
                    }

                    QQC2.Label {
                        Layout.fillWidth: true
                        visible: page.cardState === "missing" || page.cardState === "done"
                        wrapMode: Text.WordWrap
                        color: Kirigami.Theme.disabledTextColor
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        text: page.cardState === "done"
                            ? (svwr.updateAvailable ? "Version " + svwr.latest + " is available" : "Ready to use")
                            : "Plasma wallpaper plugin by luisbocanegra\ngithub.com/luisbocanegra/plasma-smart-video-wallpaper-reborn"
                    }

                    QQC2.ProgressBar {
                        Layout.fillWidth: true
                        visible: page.cardState === "running"
                        from: 0
                        to: 1
                        value: svwr.progress
                    }

                    QQC2.Label {
                        Layout.fillWidth: true
                        visible: page.cardState === "running"
                        text: svwr.stage
                        elide: Text.ElideRight
                        font.family: "monospace"
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                        color: Kirigami.Theme.disabledTextColor
                    }

                    QQC2.Label {
                        Layout.fillWidth: true
                        visible: page.cardState === "error"
                        text: svwr.error
                        wrapMode: Text.WrapAnywhere
                        maximumLineCount: 15
                        font.family: "monospace"
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                    }
                }

                ColumnLayout {
                    Layout.alignment: Qt.AlignTop

                    QQC2.Button {
                        visible: page.cardState === "missing" || (page.cardState === "error" && !svwr.installed)
                        text: page.cardState === "error" ? "Try again" : "Install"
                        icon.name: "download"
                        highlighted: true
                        onClicked: repoPrompt.startInstall()
                    }

                    QQC2.Button {
                        visible: svwr.updateAvailable && !svwr.running
                        text: "Update"
                        icon.name: "update-none"
                        highlighted: true
                        onClicked: svwr.update()
                    }

                    QQC2.Button {
                        visible: page.cardState === "error"
                        text: "Copy log"
                        icon.name: "edit-copy"
                        onClicked: svwr.copyLog()
                    }
                }
            }
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.rightMargin: Kirigami.Units.gridUnit
            visible: svwr.restartHint && !svwr.running
            type: Kirigami.MessageType.Information
            text: "Log out and back in if your live wallpaper doesn't refresh."
        }

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.rightMargin: Kirigami.Units.gridUnit
            visible: svwr.missingDeps.length > 0
            type: Kirigami.MessageType.Warning
            text: "Video playback needs these packages: " + svwr.missingDeps.join(", ")
            actions: Kirigami.Action {
                text: "Install packages"
                icon.name: "install"
                enabled: !svwr.running
                onTriggered: svwr.installDeps()
            }
        }
    }
}
