import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

QtObject {
    component Group: Rectangle {
        default property alias rows: column.data

        Layout.fillWidth: true
        implicitHeight: column.implicitHeight
        radius: Kirigami.Units.cornerRadius * 2
        color: Kirigami.Theme.alternateBackgroundColor
        border.width: 1
        border.color: Qt.alpha(Kirigami.Theme.textColor, 0.12)

        ColumnLayout {
            id: column

            anchors.left: parent.left
            anchors.right: parent.right
            spacing: 0
        }
    }

    component Row: ColumnLayout {
        id: row

        property string title
        property string subtitle
        property bool separator: true
        property bool monoSubtitle: false
        property alias leading: lead.data
        default property alias trailing: tail.data

        Layout.fillWidth: true
        spacing: 0

        Kirigami.Separator {
            Layout.fillWidth: true
            visible: row.separator
            opacity: 0.6
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.largeSpacing
            opacity: row.enabled ? 1 : 0.45

            RowLayout {
                id: lead
                visible: children.length > 0
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                QQC2.Label {
                    Layout.fillWidth: true
                    text: row.title
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                QQC2.Label {
                    Layout.fillWidth: true
                    visible: text !== ""
                    text: row.subtitle
                    color: Kirigami.Theme.disabledTextColor
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    font.family: row.monoSubtitle ? "monospace" : Kirigami.Theme.defaultFont.family
                    elide: Text.ElideRight
                }
            }

            RowLayout {
                id: tail
                spacing: Kirigami.Units.smallSpacing
            }
        }
    }

    component PageHeader: ColumnLayout {
        property alias title: heading.text
        property alias lead: leadLabel.text

        Layout.fillWidth: true
        Layout.bottomMargin: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Heading {
            id: heading
            level: 1
        }

        QQC2.Label {
            id: leadLabel
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            color: Kirigami.Theme.disabledTextColor
        }
    }
}
