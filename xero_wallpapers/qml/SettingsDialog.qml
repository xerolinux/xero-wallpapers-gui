import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kirigami.dialogs as KDialogs
import "." as App

Kirigami.Dialog {
    id: root

    property string category: "general"

    function openAt(cat) {
        category = cat
        open()
    }

    title: "Settings"
    padding: 0
    preferredWidth: 960
    preferredHeight: 610
    standardButtons: Kirigami.Dialog.NoButton
    header: KDialogs.DialogHeader {
        dialog: root

        contentItem: RowLayout {
            spacing: Kirigami.Units.smallSpacing

            KDialogs.DialogHeaderTopContent {
                Layout.fillWidth: true
                dialog: root
                showCloseButton: false
            }

            QQC2.ToolButton {
                text: "Run setup again"
                icon.name: "tools-wizard"
                QQC2.ToolTip.text: "Walk through the first-launch setup again"
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                onClicked: settings.runSetupAgain()
            }

            QQC2.ToolButton {
                icon.name: hovered ? "window-close" : "window-close-symbolic"
                text: "Close"
                display: QQC2.AbstractButton.IconOnly
                onClicked: root.reject()
            }
        }
    }

    Item {
        implicitWidth: root.preferredWidth
        implicitHeight: root.preferredHeight - (root.header ? root.header.height : 0)

        RowLayout {
            anchors.fill: parent
            spacing: 0

            ColumnLayout {
                Layout.preferredWidth: 220
                Layout.fillHeight: true
                Layout.margins: Kirigami.Units.largeSpacing
                spacing: 2

                Repeater {
                    model: [
                        { key: "general", label: "General", icon: "preferences-system" },
                        { key: "sources", label: "Sources", icon: "globe" },
                        { key: "downloads", label: "Downloads", icon: "folder-download" },
                        { key: "live", label: "Live Wallpapers", icon: "video-x-generic" }
                    ]

                    delegate: QQC2.ItemDelegate {
                        required property var modelData

                        Layout.fillWidth: true
                        text: modelData.label
                        icon.name: modelData.icon
                        highlighted: root.category === modelData.key
                        onClicked: root.category = modelData.key
                    }
                }

                Item { Layout.fillHeight: true }
            }

            Kirigami.Separator {
                Layout.fillHeight: true
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: ["general", "sources", "downloads", "live"].indexOf(root.category)

                App.GeneralPage {}
                App.SourcesPage {}
                App.DownloadsPage {}
                App.LivePage {}
            }
        }
    }
}
