import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: card

    required property int index
    required property string title
    required property string thumb
    required property string fill
    required property string resolution
    required property string source
    required property string kind
    required property real duration

    signal clicked()

    readonly property bool hovered: hover.hovered
    readonly property int radius: Kirigami.Units.cornerRadius * 2

    function formatDuration(seconds) {
        const s = Math.round(seconds)
        return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0")
    }

    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        onTapped: card.clicked()
    }

    Item {
        id: art

        width: parent.width
        height: parent.height
        y: card.hovered ? -3 : 0

        Behavior on y {
            NumberAnimation { duration: Kirigami.Units.longDuration; easing.type: Easing.OutCubic }
        }

        Kirigami.ShadowedRectangle {
            anchors.fill: parent
            radius: card.radius
            color: Kirigami.Theme.alternateBackgroundColor
            border.width: card.hovered ? 2 : 0
            border.color: Kirigami.Theme.highlightColor
            shadow.size: card.hovered ? 22 : 0
            shadow.yOffset: 8
            shadow.color: Qt.rgba(0, 0, 0, 0.35)
        }

        FitImage {
            id: image

            anchors.fill: parent
            anchors.margins: card.hovered ? 2 : 0
            radius: card.radius - anchors.margins
            source: card.thumb
            fillSource: card.fill
            sourceSize.width: Math.round(card.width * Screen.devicePixelRatio)
            opacity: status === Image.Ready ? 1 : 0

            Behavior on opacity {
                NumberAnimation { duration: Kirigami.Units.longDuration }
            }
        }

        Kirigami.Icon {
            anchors.centerIn: parent
            width: Kirigami.Units.iconSizes.large
            height: width
            source: "image-missing"
            visible: image.status === Image.Error
            opacity: 0.5
        }

        Rectangle {
            id: badge

            anchors.top: parent.top
            anchors.right: parent.right
            anchors.margins: 8
            radius: 6
            color: "#8c000000"
            visible: badgeText.text !== ""
            width: badgeText.implicitWidth + 14
            height: badgeText.implicitHeight + 4

            QQC2.Label {
                id: badgeText
                anchors.centerIn: parent
                color: "white"
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                font.weight: Font.DemiBold
                text: card.kind === "live"
                      ? (card.duration > 0 ? "▶ " + card.formatDuration(card.duration) : "▶")
                      : card.resolution
            }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: caption.implicitHeight + 36
            bottomLeftRadius: card.radius
            bottomRightRadius: card.radius
            gradient: Gradient {
                GradientStop { position: 0; color: "#00000000" }
                GradientStop { position: 1; color: "#b8000000" }
            }

            ColumnLayout {
                id: caption

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                anchors.bottomMargin: 10
                spacing: 2

                QQC2.Label {
                    Layout.fillWidth: true
                    text: card.title || card.source
                    color: "white"
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                QQC2.Label {
                    Layout.fillWidth: true
                    visible: card.title !== ""
                    text: card.source
                    color: "white"
                    opacity: 0.75
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    elide: Text.ElideRight
                }
            }
        }
    }
}
