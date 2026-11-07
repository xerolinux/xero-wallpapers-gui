import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: page

    property string kind: "static"

    readonly property int sideMargin: 26
    readonly property int gap: 18
    readonly property int minCardWidth: 180
    readonly property var items: kind === "live" ? library.liveItems : library.staticItems
    readonly property var copies: kind === "live" ? library.liveDuplicates : library.staticDuplicates
    readonly property string folder: kind === "live" ? settings.liveDir : settings.staticDir

    readonly property int maxPlayers: 4
    property int activePlayers: 0
    // Grab results must stay referenced for their image URLs to remain valid.
    property var frames: ({})
    property var failedFrames: ({})
    property int frameVersion: 0

    signal slotFreed()
    signal editRequested(string path)

    function frameFor(path) {
        frameVersion
        return frames[path] || null
    }

    function needsFrame(path) {
        frameVersion
        return !(path in frames) && !(path in failedFrames)
    }

    function storeFrame(path, result) {
        if (result)
            frames[path] = result
        else
            failedFrames[path] = true
        frameVersion++
    }

    function acquirePlayer() {
        if (activePlayers >= maxPlayers)
            return false
        activePlayers++
        return true
    }

    function releasePlayer() {
        activePlayers--
        slotFreed()
    }

    function trash(item) {
        if (item.isCurrent)
            confirmDelete.ask(item)
        else
            library.delete(item.path)
    }

    onVisibleChanged: if (visible) library.refresh()

    Connections {
        target: library

        function onTrashed(name, path) {
            applicationWindow().showPassiveNotification("Moved to Trash: " + name, "long", "Undo",
                                                         () => library.undoDelete(path))
        }

        function onDuplicatesTrashed(count, paths) {
            applicationWindow().showPassiveNotification(
                count === 1 ? "Moved 1 copy to the Trash" : "Moved " + count + " copies to the Trash", "long", "Undo",
                () => library.undoRemoveDuplicates(paths))
        }

        function onTidyDone(count) {
            applicationWindow().showPassiveNotification(
                count === 0 ? "Nothing was renamed" : count === 1 ? "Renamed 1 file" : "Renamed " + count + " files")
        }
    }

    TidyNamesDialog {
        id: tidyDialog
    }

    RemoveDuplicatesDialog {
        id: dupesDialog
    }

    Kirigami.PromptDialog {
        id: confirmDelete

        property var item: null

        function ask(it) {
            item = it
            open()
        }

        title: "Move the current wallpaper to the Trash?"
        subtitle: item ? item.name + " is your wallpaper right now. It stays on screen until you pick another one." : ""
        standardButtons: Kirigami.Dialog.NoButton
        customFooterActions: [
            Kirigami.Action {
                text: "Move to Trash"
                icon.name: "edit-delete"
                onTriggered: {
                    library.delete(confirmDelete.item.path)
                    confirmDelete.close()
                }
            },
            Kirigami.Action {
                text: "Cancel"
                icon.name: "dialog-cancel"
                onTriggered: confirmDelete.close()
            }
        ]
    }

    Connections {
        target: settings

        function onLiveEnabledChanged() {
            if (!settings.liveEnabled)
                page.kind = "static"
        }
    }

    QQC2.ScrollBar {
        id: vbar

        anchors.top: page.top
        anchors.bottom: page.bottom
        anchors.right: page.right
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: page.sideMargin
        anchors.rightMargin: page.sideMargin
        anchors.topMargin: page.gap
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.bottomMargin: 16
            spacing: Kirigami.Units.smallSpacing * 2

            Kirigami.Heading {
                text: "Library"
                level: 2
                Layout.rightMargin: Kirigami.Units.largeSpacing
            }

            Kirigami.Chip {
                text: "Wallpapers  " + library.staticItems.length
                icon.name: "preferences-desktop-wallpaper"
                checkable: true
                closable: false
                checked: page.kind === "static"
                onClicked: page.kind = "static"
            }

            Kirigami.Chip {
                visible: settings.liveEnabled
                text: "Live  " + library.liveItems.length
                icon.name: "video-x-generic"
                checkable: true
                closable: false
                checked: page.kind === "live"
                onClicked: page.kind = "live"
            }

            QQC2.Label {
                Layout.fillWidth: true
                Layout.leftMargin: Kirigami.Units.largeSpacing
                text: page.folder
                opacity: 0.6
                elide: Text.ElideMiddle
            }

            QQC2.BusyIndicator {
                running: library.busy
                visible: running
                Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                Layout.preferredHeight: Kirigami.Units.iconSizes.medium
            }

            QQC2.Button {
                text: "Tidy names"
                icon.name: "edit-rename"
                enabled: !library.tidying && page.items.length > 0
                onClicked: tidyDialog.propose(page.kind)
                QQC2.ToolTip.text: "Give coded file names readable ones"
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }

            QQC2.Button {
                text: "Remove duplicates"
                icon.name: "edit-copy"
                enabled: page.copies.length > 0
                onClicked: dupesDialog.show(page.copies)
                QQC2.ToolTip.text: "Move extra copies of the same picture to the Trash"
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }

            QQC2.Button {
                text: "Open folder"
                icon.name: "folder-open"
                onClicked: library.openFolder(page.kind)
            }
        }

        GridView {
            id: grid

            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.rightMargin: -page.gap
            bottomMargin: 90

            readonly property int columns: Math.max(1, Math.floor(width / (page.minCardWidth + page.gap)))

            cellWidth: Math.floor(width / columns)
            cellHeight: Math.round((cellWidth - page.gap) * 10 / 16) + page.gap
            clip: true
            model: page.items
            QQC2.ScrollBar.vertical: vbar

            delegate: LibraryCard {
                width: grid.cellWidth - page.gap
                height: grid.cellHeight - page.gap
            }
        }
    }

    Kirigami.PlaceholderMessage {
        anchors.centerIn: parent
        width: parent.width - Kirigami.Units.gridUnit * 4
        visible: grid.count === 0 && !library.busy
        icon.name: page.kind === "live" ? "video-x-generic" : "folder-pictures"
        text: page.kind === "live" ? "No live wallpapers yet" : "No wallpapers yet"
        explanation: "Downloads land in " + page.folder
    }

    component LibraryCard: Item {
        id: card

        required property var modelData
        readonly property bool hovered: hover.hovered
        readonly property int radius: Kirigami.Units.cornerRadius * 2
        readonly property bool live: page.kind === "live"
        readonly property var frame: live ? page.frameFor(modelData.path) : null
        readonly property bool wantsPlayer: live && page.visible && page.needsFrame(modelData.path)
        property bool holding: false

        function tryStart() {
            if (wantsPlayer && !holding && page.acquirePlayer())
                holding = true
        }

        function stop() {
            if (holding) {
                holding = false
                page.releasePlayer()
            }
        }

        function done(result) {
            if (result)
                library.frameGrabbed(modelData.path, result.image)
            page.storeFrame(modelData.path, result)
            stop()
        }

        onWantsPlayerChanged: wantsPlayer ? tryStart() : stop()
        Component.onCompleted: tryStart()
        Component.onDestruction: stop()

        Connections {
            target: page

            function onSlotFreed() {
                card.tryStart()
            }
        }

        HoverHandler {
            id: hover
        }

        Kirigami.ShadowedRectangle {
            anchors.fill: parent
            radius: card.radius
            color: Kirigami.Theme.alternateBackgroundColor
            border.width: card.modelData.isCurrent || card.hovered ? 2 : 0
            border.color: Kirigami.Theme.highlightColor
        }

        Kirigami.Icon {
            anchors.centerIn: parent
            width: Kirigami.Units.iconSizes.large
            height: width
            source: card.live ? "video-x-generic" : "image-x-generic"
            visible: image.status !== Image.Ready
            opacity: 0.5
        }

        Loader {
            id: videoLoader

            anchors.fill: parent
            active: card.holding
            asynchronous: true
            source: "VideoThumb.qml"
            onLoaded: item.source = card.modelData.url
            onStatusChanged: if (status === Loader.Error) card.done(null)

            Connections {
                target: videoLoader.item
                ignoreUnknownSignals: true

                function onGrabbed(result) {
                    card.done(result)
                }
            }
        }

        FitImage {
            id: image

            anchors.fill: parent
            anchors.margins: card.modelData.isCurrent || card.hovered ? 2 : 0
            radius: card.radius - anchors.margins
            source: card.live ? (card.frame ? card.frame.url : "") : card.modelData.url
            fillSource: card.live ? source : card.modelData.fill
            blurFill: card.live
            // Grabbed frames are already card-sized and reject sourceSize.
            sourceSize: card.live ? undefined : Qt.size(Math.round(card.width * Screen.devicePixelRatio),
                                                        Math.round(card.height * Screen.devicePixelRatio))
        }

        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.margins: 8
            visible: card.modelData.isCurrent
            radius: 6
            color: Kirigami.Theme.highlightColor
            width: currentLabel.implicitWidth + 14
            height: currentLabel.implicitHeight + 4

            QQC2.Label {
                id: currentLabel
                anchors.centerIn: parent
                text: "Current"
                color: Kirigami.Theme.highlightedTextColor
                font.pointSize: Kirigami.Theme.smallFont.pointSize
                font.weight: Font.DemiBold
            }
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: caption.implicitHeight + 30
            bottomLeftRadius: card.radius
            bottomRightRadius: card.radius
            gradient: Gradient {
                GradientStop { position: 0; color: "#00000000" }
                GradientStop { position: 1; color: "#b8000000" }
            }

            RowLayout {
                id: caption

                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.leftMargin: 10
                anchors.rightMargin: 6
                anchors.bottomMargin: 6
                spacing: 2

                QQC2.Label {
                    Layout.fillWidth: true
                    text: card.modelData.name
                    color: "white"
                    font.weight: Font.DemiBold
                    elide: Text.ElideMiddle
                }

                QQC2.ToolButton {
                    visible: card.hovered
                    icon.name: "checkmark"
                    icon.color: "white"
                    enabled: !card.modelData.isCurrent
                    onClicked: library.setWallpaper(card.modelData.path)
                    QQC2.ToolTip.text: "Set as wallpaper"
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                }

                QQC2.ToolButton {
                    visible: card.hovered && !card.live
                    icon.name: "transform-crop"
                    icon.color: "white"
                    onClicked: page.editRequested(card.modelData.path)
                    QQC2.ToolTip.text: "Edit: crop & upscale"
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                }

                QQC2.ToolButton {
                    visible: card.hovered
                    icon.name: "edit-delete"
                    icon.color: "white"
                    onClicked: page.trash(card.modelData)
                    QQC2.ToolTip.text: "Move to Trash"
                    QQC2.ToolTip.visible: hovered
                    QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                }
            }
        }
    }
}
