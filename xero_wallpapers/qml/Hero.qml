import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: hero

    property url logoUrl

    signal detailsRequested()
    signal fullscreenRequested()

    readonly property var item: browse.featured
    readonly property bool live: item.kind === "live"
    readonly property int radius: Kirigami.Units.cornerRadius * 2

    function meta() {
        const parts = []
        if (item.resolution)
            parts.push(item.resolution)
        if (item.author)
            parts.push("by " + item.author)
        if (live && item.duration > 0)
            parts.push(Math.round(item.duration) + " s loop")
        return parts.join(" · ")
    }

    Kirigami.ShadowedRectangle {
        anchors.fill: parent
        radius: hero.radius
        color: Kirigami.Theme.alternateBackgroundColor
    }

    Kirigami.ShadowedImage {
        id: art

        anchors.fill: parent
        radius: hero.radius
        color: "transparent"
        source: hero.item.image || ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        sourceSize.width: Math.round(hero.width * Screen.devicePixelRatio)
        opacity: status === Image.Ready ? 1 : 0

        Behavior on opacity {
            NumberAnimation { duration: Kirigami.Units.veryLongDuration }
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: hero.radius
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "#b3000000" }
            GradientStop { position: 0.6; color: "#26000000" }
            GradientStop { position: 1; color: "#00000000" }
        }
    }

    RowLayout {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: 20
        spacing: Kirigami.Units.smallSpacing * 2

        Image {
            source: hero.logoUrl
            sourceSize.width: Kirigami.Units.iconSizes.smallMedium
            sourceSize.height: Kirigami.Units.iconSizes.smallMedium
        }

        QQC2.Label {
            text: "Xero Wallpapers"
            color: "white"
            font.weight: Font.DemiBold
        }
    }

    ColumnLayout {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.leftMargin: 34
        anchors.bottomMargin: 30
        width: Math.min(520, hero.width - 68)
        spacing: 0
        visible: hero.item.title !== undefined

        QQC2.Label {
            text: (hero.live ? "Featured live wallpaper" : "Featured")
                  + (hero.item.title && hero.item.source ? " · " + hero.item.source : "")
            color: "white"
            opacity: 0.8
            font.capitalization: Font.AllUppercase
            font.letterSpacing: 1.5
            font.pointSize: Kirigami.Theme.smallFont.pointSize
        }

        QQC2.Label {
            Layout.fillWidth: true
            Layout.topMargin: 6
            Layout.bottomMargin: 8
            text: hero.item.title || hero.item.source || ""
            color: "white"
            font.pixelSize: 38
            font.weight: Font.Bold
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        QQC2.Label {
            Layout.bottomMargin: 18
            text: hero.meta()
            color: "white"
            opacity: 0.8
            visible: text !== ""
        }

        RowLayout {
            spacing: 10

            QQC2.Button {
                text: "Browse fullscreen"
                icon.name: "view-fullscreen"
                highlighted: true
                enabled: hero.item.title !== undefined
                onClicked: hero.fullscreenRequested()
            }

            QQC2.Button {
                text: "Details"
                icon.name: "documentinfo"
                onClicked: hero.detailsRequested()
            }
        }
    }

    QQC2.BusyIndicator {
        anchors.centerIn: parent
        running: art.status !== Image.Ready && browse.busy
        visible: running
    }
}
