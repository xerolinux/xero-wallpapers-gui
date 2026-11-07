import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Effects
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "." as App

App.ModalCard {
    id: about

    property url logoUrl
    readonly property int band: 160

    preferredWidth: 480
    preferredHeight: 520
    closePolicy: QQC2.Popup.CloseOnEscape | QQC2.Popup.CloseOnPressOutside

    component LinkCard: Rectangle {
        id: link

        property string icon
        property string title
        property string url

        Layout.fillWidth: true
        Layout.preferredWidth: 1
        implicitHeight: linkCol.implicitHeight + Kirigami.Units.gridUnit * 1.5
        radius: Kirigami.Units.cornerRadius * 2
        color: hover.hovered ? Qt.alpha(Kirigami.Theme.highlightColor, 0.12) : Kirigami.Theme.alternateBackgroundColor
        border.width: 1
        border.color: hover.hovered ? Kirigami.Theme.highlightColor : Qt.alpha(Kirigami.Theme.textColor, 0.1)

        Behavior on color {
            ColorAnimation { duration: Kirigami.Units.shortDuration }
        }

        HoverHandler {
            id: hover
            cursorShape: Qt.PointingHandCursor
        }

        TapHandler {
            onTapped: Qt.openUrlExternally(link.url)
        }

        Accessible.role: Accessible.Link
        Accessible.name: title

        ColumnLayout {
            id: linkCol

            anchors.fill: parent
            anchors.margins: Kirigami.Units.gridUnit * 0.75
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Icon {
                source: link.icon
                implicitWidth: Kirigami.Units.iconSizes.medium
                implicitHeight: implicitWidth
            }

            QQC2.Label {
                Layout.fillWidth: true
                text: link.title
                font.weight: Font.DemiBold
            }

            QQC2.Label {
                Layout.fillWidth: true
                text: link.url.replace(/^https:\/\/(github\.com\/)?/, "")
                color: Kirigami.Theme.disabledTextColor
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                elide: Text.ElideRight
            }
        }
    }

    Item {
        anchors.fill: parent

        Item {
            id: hero

            width: parent.width
            height: about.band

            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Kirigami.Theme.highlightColor }
                    GradientStop { position: 1; color: Qt.darker(Kirigami.Theme.highlightColor, 1.8) }
                }
            }

            Image {
                id: heroImage
                anchors.fill: parent
                source: browse.featured.image || ""
                sourceSize.width: 640
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: false
            }

            MultiEffect {
                anchors.fill: parent
                source: heroImage
                opacity: heroImage.status === Image.Ready ? 0.85 : 0
                autoPaddingEnabled: false
                blurEnabled: true
                blur: 0.8
                blurMax: 48
            }

            Rectangle {
                anchors.fill: parent
                color: Qt.alpha(Kirigami.Theme.highlightColor, 0.35)
            }
        }

        Rectangle {
            id: logoDisc

            anchors.horizontalCenter: parent.horizontalCenter
            y: about.band - height / 2
            width: 112
            height: 112
            radius: width / 2
            color: Kirigami.Theme.backgroundColor
            border.width: 1
            border.color: Qt.alpha(Kirigami.Theme.textColor, 0.12)

            Image {
                anchors.centerIn: parent
                width: 96
                height: 96
                source: about.logoUrl
                sourceSize: Qt.size(192, 192)
                fillMode: Image.PreserveAspectFit
                smooth: true
            }
        }

        ColumnLayout {
            anchors.top: logoDisc.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.topMargin: Kirigami.Units.largeSpacing
            anchors.leftMargin: Kirigami.Units.gridUnit * 1.5
            anchors.rightMargin: Kirigami.Units.gridUnit * 1.5
            anchors.bottomMargin: Kirigami.Units.gridUnit
            spacing: Kirigami.Units.largeSpacing

            Kirigami.Heading {
                Layout.alignment: Qt.AlignHCenter
                level: 1
                text: "Xero Wallpapers"
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: Kirigami.Units.largeSpacing

                Rectangle {
                    implicitWidth: versionLabel.implicitWidth + Kirigami.Units.largeSpacing * 2
                    implicitHeight: versionLabel.implicitHeight + Kirigami.Units.smallSpacing
                    radius: height / 2
                    color: Qt.alpha(Kirigami.Theme.highlightColor, 0.15)

                    QQC2.Label {
                        id: versionLabel
                        anchors.centerIn: parent
                        text: "Version " + appVersion
                        color: Kirigami.Theme.highlightColor
                        font.weight: Font.DemiBold
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                    }
                }

                QQC2.Label {
                    text: "GPL-3.0"
                    color: Kirigami.Theme.disabledTextColor
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                }
            }

            QQC2.Label {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: "Browse, preview, upscale and set wallpapers and live wallpapers on KDE Plasma."
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.largeSpacing
                spacing: Kirigami.Units.largeSpacing

                LinkCard {
                    icon: "code-context"
                    title: "Source code"
                    url: "https://github.com/xerolinux/xero-wallpapers-gui"
                }

                LinkCard {
                    icon: "system-users"
                    title: "Community"
                    url: "https://discord.xerolinux.xyz"
                }
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true

                QQC2.Label {
                    Layout.fillWidth: true
                    text: "Built with AI help · Made for the XeroLinux community"
                    color: Kirigami.Theme.disabledTextColor
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    elide: Text.ElideRight
                }

                QQC2.Button {
                    text: "Close"
                    onClicked: about.close()
                }
            }
        }
    }
}
