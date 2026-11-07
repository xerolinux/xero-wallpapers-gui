import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Dialogs
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "." as App

QQC2.ScrollView {
    id: page

    contentWidth: availableWidth
    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

    FolderDialog {
        id: picker

        property string kind

        function pick(k, path) {
            kind = k
            currentFolder = "file://" + path
            open()
        }

        title: kind === "live" ? "Live wallpapers folder" : "Wallpapers folder"
        onAccepted: settings.setDir(kind, selectedFolder.toString())
    }

    component PathLabel: QQC2.Label {
        Layout.maximumWidth: 330
        leftPadding: Kirigami.Units.smallSpacing * 2
        rightPadding: leftPadding
        topPadding: Kirigami.Units.smallSpacing
        bottomPadding: topPadding
        font.family: "monospace"
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        elide: Text.ElideMiddle
        background: Rectangle {
            radius: Kirigami.Units.cornerRadius
            color: Kirigami.Theme.backgroundColor
            border.width: 1
            border.color: Qt.alpha(Kirigami.Theme.textColor, 0.12)
        }
    }

    ColumnLayout {
        width: page.availableWidth
        spacing: Kirigami.Units.largeSpacing

        App.SettingsParts.PageHeader {
            Layout.margins: Kirigami.Units.gridUnit
            Layout.bottomMargin: 0
            title: "Downloads"
            lead: "Wallpapers and live wallpapers are saved to separate folders."
        }

        App.SettingsParts.Group {
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.rightMargin: Kirigami.Units.gridUnit

            App.SettingsParts.Row {
                separator: false
                title: "Wallpapers folder"
                subtitle: "Static images (JPEG, PNG, WebP)"
                leading: Kirigami.Icon {
                    source: "folder-pictures"
                    implicitWidth: Kirigami.Units.iconSizes.medium
                    implicitHeight: implicitWidth
                }

                PathLabel { text: settings.staticDir }

                QQC2.Button {
                    text: "Change…"
                    onClicked: picker.pick("static", settings.staticDir)
                }
            }

            App.SettingsParts.Row {
                enabled: settings.liveEnabled
                title: "Live wallpapers folder"
                subtitle: settings.liveEnabled ? "Videos (MP4, WebM)" : "Turn on Live Wallpapers to use this"
                leading: Kirigami.Icon {
                    source: "folder-videos"
                    implicitWidth: Kirigami.Units.iconSizes.medium
                    implicitHeight: implicitWidth
                }

                PathLabel { text: settings.liveDir }

                QQC2.Button {
                    text: "Change…"
                    onClicked: picker.pick("live", settings.liveDir)
                }
            }
        }

        App.SettingsParts.Group {
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.rightMargin: Kirigami.Units.gridUnit

            App.SettingsParts.Row {
                separator: false
                title: "Skip duplicates"
                subtitle: "Don't download a picture that's already in your Library, even at another size or format"

                QQC2.Switch {
                    checked: settings.skipDuplicates
                    onToggled: settings.skipDuplicates = checked
                }
            }
        }
    }
}
