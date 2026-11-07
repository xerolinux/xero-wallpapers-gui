import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import QtMultimedia
import org.kde.kirigami as Kirigami

Kirigami.Dialog {
    id: sheet

    readonly property var item: detail.item
    readonly property bool live: item.kind === "live"
    readonly property bool busy: progress >= 0
    readonly property int radius: Kirigami.Units.cornerRadius * 2

    property real progress: -1
    property string message: ""
    property int messageType: Kirigami.MessageType.Information
    property bool previewFailed: false

    signal cropRequested(int index)

    function show(index) {
        progress = -1
        message = ""
        previewFailed = false
        detail.open(index)
        open()
    }

    function displayTitle() {
        return item.title || item.sourceLabel || ""
    }

    function byline() {
        const parts = [item.author ? "by " + item.author : "", item.title ? item.sourceLabel : ""]
        return parts.filter(p => p).join(" · ")
    }

    // DownloadController names untitled items by their source label.
    function mine(title) {
        return visible && title === displayTitle()
    }

    header: null
    padding: 22
    preferredWidth: 960
    preferredHeight: 560

    Connections {
        target: downloads

        function onProgress(title, done, total) {
            if (!sheet.mine(title))
                return
            sheet.progress = total > 0 ? done / total : 0
            sheet.messageType = Kirigami.MessageType.Information
            sheet.message = total > 0 ? "Downloading… " + Math.round(done * 100 / total) + "%" : "Downloading…"
        }

        function onFinished(title, path, wasSet, existing) {
            if (!sheet.mine(title))
                return
            sheet.progress = -1
            sheet.messageType = Kirigami.MessageType.Positive
            if (existing)
                sheet.message = "Already in your Library" + (wasSet ? " · set as wallpaper" : "")
            else
                sheet.message = wasSet ? "Set as wallpaper" : "Saved to " + path
        }

        function onFailed(title, message) {
            if (!sheet.mine(title))
                return
            sheet.progress = -1
            sheet.messageType = Kirigami.MessageType.Error
            sheet.message = message
        }
    }

    component SectionLabel: QQC2.Label {
        color: Kirigami.Theme.disabledTextColor
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 1.2
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        font.weight: Font.DemiBold
    }

    Item {
        implicitWidth: sheet.preferredWidth - sheet.leftPadding - sheet.rightPadding
        implicitHeight: sheet.preferredHeight - sheet.topPadding - sheet.bottomPadding

        RowLayout {
            id: body

            anchors.fill: parent
            spacing: 24

            Item {
                id: preview

                Layout.fillHeight: true
                Layout.preferredWidth: Math.round(body.width * 1.45 / 2.45)

                Kirigami.ShadowedRectangle {
                    anchors.fill: parent
                    radius: sheet.radius
                    color: Kirigami.Theme.alternateBackgroundColor
                }

                FitImage {
                    anchors.fill: parent
                    radius: sheet.radius
                    source: sheet.item.thumb || ""
                    fillSource: sheet.item.fill || ""
                    sourceSize.width: Math.round(width * Screen.devicePixelRatio)
                }

                FitImage {
                    id: full

                    anchors.fill: parent
                    radius: sheet.radius
                    source: sheet.visible && sheet.item.image ? sheet.item.image : ""
                    sourceSize.width: Math.round(width * Screen.devicePixelRatio)
                    opacity: status === Image.Ready ? 1 : 0

                    Behavior on opacity {
                        NumberAnimation { duration: Kirigami.Units.longDuration }
                    }
                }

                // A fresh player per clip: Video's autoPlay only fires for the first source it is given.
                Loader {
                    id: video

                    readonly property bool started: item !== null && item.started

                    anchors.fill: parent
                    active: sheet.visible && !sheet.previewFailed && (sheet.item.video || "") !== ""
                    sourceComponent: Video {
                        property bool started: false

                        source: sheet.item.video
                        autoPlay: true
                        muted: true
                        loops: MediaPlayer.Infinite
                        fillMode: VideoOutput.PreserveAspectFit
                        visible: started
                        onPositionChanged: if (position > 0 && playbackState === MediaPlayer.PlayingState) started = true
                        onErrorOccurred: sheet.previewFailed = true
                    }
                }

                Timer {
                    interval: 15000
                    running: video.active && !video.started
                    onTriggered: sheet.previewFailed = true
                }

                QQC2.BusyIndicator {
                    anchors.centerIn: parent
                    running: full.status === Image.Loading || (video.active && !video.started)
                    visible: running
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true

                    Kirigami.Heading {
                        Layout.fillWidth: true
                        text: sheet.displayTitle()
                        level: 1
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }

                    QQC2.ToolButton {
                        Layout.alignment: Qt.AlignTop
                        icon.name: "dialog-close"
                        text: "Close"
                        display: QQC2.AbstractButton.IconOnly
                        onClicked: sheet.close()
                    }
                }

                QQC2.Label {
                    Layout.fillWidth: true
                    text: sheet.byline()
                    color: Kirigami.Theme.disabledTextColor
                    elide: Text.ElideRight
                }

                RowLayout {
                    Layout.topMargin: Kirigami.Units.largeSpacing
                    Layout.bottomMargin: Kirigami.Units.smallSpacing
                    spacing: Kirigami.Units.smallSpacing * 2

                    QQC2.Button {
                        text: "Download"
                        icon.name: "download"
                        highlighted: true
                        enabled: !sheet.busy
                        onClicked: downloads.download(sheet.item.index, false)
                    }

                    QQC2.Button {
                        text: "Set"
                        icon.name: "preferences-desktop-wallpaper"
                        enabled: !sheet.busy
                        onClicked: downloads.setWallpaper(sheet.item.index)
                    }

                    QQC2.Button {
                        text: "Crop & Upscale"
                        icon.name: "transform-crop"
                        visible: !sheet.live
                        enabled: !sheet.busy
                        onClicked: sheet.cropRequested(sheet.item.index)
                    }
                }

                Kirigami.InlineMessage {
                    Layout.fillWidth: true
                    type: sheet.messageType
                    text: sheet.message
                    visible: sheet.message !== ""
                    showCloseButton: !sheet.busy
                    onVisibleChanged: if (!visible) sheet.message = ""
                }

                QQC2.ProgressBar {
                    Layout.fillWidth: true
                    visible: sheet.busy
                    value: sheet.progress
                    indeterminate: sheet.progress === 0
                }

                QQC2.ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentWidth: availableWidth

                    ColumnLayout {
                        width: parent.width
                        spacing: Kirigami.Units.smallSpacing

                        RowLayout {
                            Layout.topMargin: Kirigami.Units.largeSpacing

                            SectionLabel { text: "Metadata" }

                            QQC2.BusyIndicator {
                                running: detail.loading
                                visible: running
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                            }
                        }

                        Repeater {
                            model: sheet.item.rows || []

                            delegate: RowLayout {
                                required property var modelData

                                Layout.fillWidth: true
                                spacing: Kirigami.Units.largeSpacing

                                QQC2.Label {
                                    Layout.preferredWidth: Kirigami.Units.gridUnit * 8
                                    text: modelData.k
                                    color: Kirigami.Theme.disabledTextColor
                                }

                                QQC2.Label {
                                    Layout.fillWidth: true
                                    text: modelData.v
                                    font.weight: Font.Medium
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        SectionLabel {
                            Layout.topMargin: Kirigami.Units.largeSpacing
                            text: "Tags"
                            visible: tags.count > 0
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            Repeater {
                                id: tags

                                model: sheet.item.tags || []

                                delegate: Kirigami.Chip {
                                    required property string modelData

                                    text: "#" + modelData
                                    closable: false
                                    checkable: false
                                    interactive: false
                                }
                            }
                        }

                        SectionLabel {
                            Layout.topMargin: Kirigami.Units.largeSpacing
                            text: "Palette"
                            visible: swatches.count > 0
                        }

                        Row {
                            spacing: Kirigami.Units.smallSpacing

                            Repeater {
                                id: swatches

                                model: sheet.item.palette || []

                                delegate: Rectangle {
                                    required property string modelData

                                    width: Kirigami.Units.iconSizes.smallMedium
                                    height: width
                                    radius: Kirigami.Units.cornerRadius
                                    color: modelData
                                    border.width: 1
                                    border.color: Qt.alpha(Kirigami.Theme.textColor, 0.15)

                                    QQC2.ToolTip.text: modelData
                                    QQC2.ToolTip.visible: swatchHover.hovered

                                    HoverHandler { id: swatchHover }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
