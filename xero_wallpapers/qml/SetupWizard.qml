import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Dialogs
import QtQuick.Effects
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "." as App

App.ModalCard {
    id: wizard

    property url logoUrl
    property int step: 0
    readonly property var steps: ["Welcome", "Wallpapers", "Live wallpapers", "Preferences", "All set"]
    readonly property int lastStep: steps.length - 1
    property bool finished: false
    property bool clearing: false
    property string freed: ""

    property string staticDir
    property string liveDir
    property bool liveEnabled
    property bool safeContent
    property bool matchScreen
    property bool skipDuplicates
    property int cacheSizeMb

    function start() {
        staticDir = settings.staticDir
        liveDir = settings.liveDir
        liveEnabled = settings.liveEnabled
        safeContent = settings.safeContent
        matchScreen = settings.matchScreen
        skipDuplicates = settings.skipDuplicates
        cacheSizeMb = settings.cacheSizeMb
        step = 0
        finished = false
        freed = ""
        open()
    }

    function next() {
        if (step < lastStep)
            step += 1
        else
            finish()
    }

    function finish() {
        finished = true
        settings.finishSetup({
            staticDir: staticDir,
            liveDir: liveDir,
            liveEnabled: liveEnabled && svwr.installed,
            safeContent: safeContent,
            matchScreen: matchScreen,
            skipDuplicates: skipDuplicates,
            cacheSizeMb: cacheSizeMb
        })
        close()
    }

    function localPath(url) {
        return decodeURIComponent(url.toString().replace(/^file:\/\//, ""))
    }

    function cacheLabel(size) {
        return size >= 1000 ? (size / 1000) + " GB" : size + " MB"
    }

    preferredWidth: 860
    preferredHeight: 580
    closePolicy: QQC2.Popup.CloseOnEscape
    onClosed: {
        if (!finished)
            settings.skipSetup()
    }

    Connections {
        target: settings

        function onCacheCleared(size) {
            wizard.clearing = false
            wizard.freed = size
        }
    }

    FolderDialog {
        id: picker

        property string kind

        function pick(k, path) {
            kind = k
            currentFolder = "file://" + path
            open()
        }

        title: kind === "live" ? "Live wallpapers folder" : "Wallpapers folder"
        onAccepted: {
            if (kind === "live")
                wizard.liveDir = wizard.localPath(selectedFolder)
            else
                wizard.staticDir = wizard.localPath(selectedFolder)
        }
    }

    App.SvwrRepoPrompt {
        id: repoPrompt
    }

    component Tile: Rectangle {
        radius: Kirigami.Units.cornerRadius * 2
        color: Kirigami.Theme.alternateBackgroundColor
        border.width: 1
        border.color: Qt.alpha(Kirigami.Theme.textColor, 0.1)
    }

    component PageHeader: RowLayout {
        property alias icon: headerIcon.source
        property alias title: heading.text
        property alias subtitle: sub.text

        Layout.fillWidth: true
        Layout.bottomMargin: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.gridUnit

        Kirigami.Icon {
            id: headerIcon
            implicitWidth: 64
            implicitHeight: 64
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Heading {
                id: heading
                Layout.fillWidth: true
                level: 1
                wrapMode: Text.WordWrap
            }

            QQC2.Label {
                id: sub
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: Kirigami.Theme.disabledTextColor
            }
        }
    }

    component OptionCard: Tile {
        id: option

        property string icon
        property string title
        property string description
        default property alias trailing: tail.data

        Layout.fillWidth: true
        implicitHeight: optionRow.implicitHeight + Kirigami.Units.largeSpacing * 2

        RowLayout {
            id: optionRow

            anchors.fill: parent
            anchors.leftMargin: Kirigami.Units.largeSpacing * 2
            anchors.rightMargin: Kirigami.Units.largeSpacing * 2
            spacing: Kirigami.Units.largeSpacing * 2
            opacity: option.enabled ? 1 : 0.45

            Kirigami.Icon {
                source: option.icon
                implicitWidth: Kirigami.Units.iconSizes.medium
                implicitHeight: implicitWidth
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                QQC2.Label {
                    Layout.fillWidth: true
                    text: option.title
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                QQC2.Label {
                    Layout.fillWidth: true
                    text: option.description
                    color: Kirigami.Theme.disabledTextColor
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    elide: Text.ElideRight
                }
            }

            RowLayout {
                id: tail
                spacing: Kirigami.Units.smallSpacing
            }
        }
    }

    component FolderCard: Tile {
        id: folder

        property string kind
        property string path
        property string icon

        Layout.fillWidth: true
        implicitHeight: folderRow.implicitHeight + Kirigami.Units.gridUnit * 1.5

        RowLayout {
            id: folderRow

            anchors.fill: parent
            anchors.leftMargin: Kirigami.Units.gridUnit
            anchors.rightMargin: Kirigami.Units.gridUnit
            spacing: Kirigami.Units.gridUnit
            opacity: folder.enabled ? 1 : 0.45

            Kirigami.Icon {
                source: folder.icon
                implicitWidth: Kirigami.Units.iconSizes.large
                implicitHeight: implicitWidth
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                QQC2.Label {
                    Layout.fillWidth: true
                    text: folder.path.split("/").filter(p => p !== "").pop() || "/"
                    font.weight: Font.Bold
                    font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.15
                    elide: Text.ElideRight
                }

                QQC2.Label {
                    Layout.fillWidth: true
                    text: folder.path
                    color: Kirigami.Theme.disabledTextColor
                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                    elide: Text.ElideMiddle
                }
            }

            QQC2.Button {
                text: "Change…"
                icon.name: "document-open-folder"
                onClicked: picker.pick(folder.kind, folder.path)
            }
        }
    }

    component Pill: Rectangle {
        property alias text: pillLabel.text
        property color textColor: Kirigami.Theme.textColor

        implicitWidth: pillLabel.implicitWidth + Kirigami.Units.largeSpacing * 2
        implicitHeight: pillLabel.implicitHeight + Kirigami.Units.smallSpacing
        radius: height / 2

        QQC2.Label {
            id: pillLabel
            anchors.centerIn: parent
            color: parent.textColor
            font.pointSize: Kirigami.Theme.smallFont.pointSize
            font.weight: Font.DemiBold
        }
    }

    component SummaryRow: RowLayout {
        property alias icon: rowIcon.source
        property alias label: key.text
        property alias value: val.text

        Layout.fillWidth: true
        spacing: Kirigami.Units.largeSpacing

        Kirigami.Icon {
            id: rowIcon
            implicitWidth: Kirigami.Units.iconSizes.smallMedium
            implicitHeight: implicitWidth
        }

        QQC2.Label {
            id: key
            Layout.preferredWidth: Kirigami.Units.gridUnit * 10
            color: Kirigami.Theme.disabledTextColor
        }

        QQC2.Label {
            id: val
            Layout.fillWidth: true
            font.weight: Font.DemiBold
            elide: Text.ElideMiddle
        }
    }

    component WizardPage: QQC2.ScrollView {
        id: wpage

        property int index
        default property alias body: column.data

        width: parent.width
        height: parent.height
        padding: Kirigami.Units.gridUnit * 2
        contentWidth: availableWidth
        QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff
        x: index === wizard.step ? 0 : index < wizard.step ? -Kirigami.Units.gridUnit * 3 : Kirigami.Units.gridUnit * 3
        opacity: index === wizard.step ? 1 : 0
        visible: opacity > 0

        Behavior on x {
            NumberAnimation { duration: Kirigami.Units.longDuration; easing.type: Easing.OutCubic }
        }

        Behavior on opacity {
            NumberAnimation { duration: Kirigami.Units.longDuration; easing.type: Easing.OutCubic }
        }

        ColumnLayout {
            id: column

            width: wpage.availableWidth
            spacing: Kirigami.Units.largeSpacing * 2
        }
    }

    Item {
        anchors.fill: parent
        focus: true
        Keys.onReturnPressed: wizard.next()
        Keys.onEnterPressed: wizard.next()

        RowLayout {
            anchors.fill: parent
            spacing: 0

            Rectangle {
                Layout.preferredWidth: 220
                Layout.fillHeight: true
                color: Kirigami.Theme.alternateBackgroundColor

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.gridUnit * 1.5
                    spacing: Kirigami.Units.gridUnit * 1.5

                    RowLayout {
                        spacing: Kirigami.Units.largeSpacing

                        Image {
                            Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                            Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                            source: wizard.logoUrl
                            sourceSize: Qt.size(64, 64)
                            fillMode: Image.PreserveAspectFit
                        }

                        ColumnLayout {
                            spacing: 0

                            QQC2.Label {
                                text: "Xero Wallpapers"
                                font.weight: Font.Bold
                            }

                            QQC2.Label {
                                text: "Setup"
                                color: Kirigami.Theme.disabledTextColor
                                font.pointSize: Kirigami.Theme.smallFont.pointSize
                            }
                        }
                    }

                    Item {
                        id: rail

                        readonly property int rowHeight: Kirigami.Units.gridUnit * 3
                        readonly property int dot: 30

                        Layout.fillWidth: true
                        Layout.preferredHeight: rowHeight * wizard.steps.length

                        Rectangle {
                            x: rail.dot / 2 - 1
                            y: rail.rowHeight / 2
                            width: 2
                            height: rail.rowHeight * wizard.lastStep
                            color: Qt.alpha(Kirigami.Theme.textColor, 0.15)
                        }

                        Rectangle {
                            x: rail.dot / 2 - 1
                            y: rail.rowHeight / 2
                            width: 2
                            height: rail.rowHeight * wizard.step
                            color: Kirigami.Theme.highlightColor

                            Behavior on height {
                                NumberAnimation { duration: Kirigami.Units.longDuration; easing.type: Easing.OutCubic }
                            }
                        }

                        Repeater {
                            model: wizard.steps

                            delegate: RowLayout {
                                id: stepRow

                                required property int index
                                required property string modelData
                                readonly property bool current: index === wizard.step
                                readonly property bool done: index < wizard.step

                                y: index * rail.rowHeight
                                width: rail.width
                                height: rail.rowHeight
                                spacing: Kirigami.Units.largeSpacing

                                Rectangle {
                                    Layout.preferredWidth: rail.dot
                                    Layout.preferredHeight: rail.dot
                                    radius: rail.dot / 2
                                    color: stepRow.current || stepRow.done ? Kirigami.Theme.highlightColor
                                        : Kirigami.Theme.alternateBackgroundColor
                                    border.width: 2
                                    border.color: stepRow.current || stepRow.done ? Kirigami.Theme.highlightColor
                                        : Qt.alpha(Kirigami.Theme.textColor, 0.25)

                                    Behavior on color {
                                        ColorAnimation { duration: Kirigami.Units.longDuration }
                                    }

                                    Kirigami.Icon {
                                        anchors.centerIn: parent
                                        visible: stepRow.done
                                        source: "checkmark"
                                        color: Kirigami.Theme.highlightedTextColor
                                        isMask: true
                                        implicitWidth: Kirigami.Units.iconSizes.small
                                        implicitHeight: implicitWidth
                                    }

                                    QQC2.Label {
                                        anchors.centerIn: parent
                                        visible: !stepRow.done
                                        text: stepRow.index + 1
                                        font.weight: Font.Bold
                                        color: stepRow.current ? Kirigami.Theme.highlightedTextColor
                                            : Kirigami.Theme.disabledTextColor
                                    }
                                }

                                QQC2.Label {
                                    Layout.fillWidth: true
                                    text: stepRow.modelData
                                    elide: Text.ElideRight
                                    font.weight: stepRow.current ? Font.Bold : Font.Normal
                                    color: stepRow.current || stepRow.done ? Kirigami.Theme.textColor
                                        : Kirigami.Theme.disabledTextColor
                                }
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }
                }
            }

            Kirigami.Separator {
                Layout.fillHeight: true
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true

                    WizardPage {
                        index: 0

                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Kirigami.Units.gridUnit * 11

                            Rectangle {
                                id: heroMask
                                anchors.fill: parent
                                radius: Kirigami.Units.cornerRadius * 3
                                visible: false
                                layer.enabled: true
                            }

                            Item {
                                anchors.fill: parent
                                layer.enabled: true
                                layer.effect: MultiEffect {
                                    maskEnabled: true
                                    maskSource: heroMask
                                    maskThresholdMin: 0.5
                                    maskSpreadAtMin: 1
                                }

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
                                    sourceSize.width: 960
                                    fillMode: Image.PreserveAspectCrop
                                    asynchronous: true
                                    visible: false
                                }

                                MultiEffect {
                                    anchors.fill: parent
                                    source: heroImage
                                    opacity: heroImage.status === Image.Ready ? 1 : 0
                                    autoPaddingEnabled: false
                                    blurEnabled: true
                                    blur: 0.7
                                    blurMax: 48
                                    brightness: -0.1

                                    Behavior on opacity {
                                        NumberAnimation { duration: Kirigami.Units.veryLongDuration }
                                    }
                                }

                                Rectangle {
                                    anchors.fill: parent
                                    color: Qt.rgba(0, 0, 0, 0.3)
                                }
                            }

                            ColumnLayout {
                                anchors.centerIn: parent
                                spacing: Kirigami.Units.largeSpacing

                                Image {
                                    Layout.alignment: Qt.AlignHCenter
                                    Layout.preferredWidth: 96
                                    Layout.preferredHeight: 96
                                    source: wizard.logoUrl
                                    sourceSize: Qt.size(192, 192)
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true
                                }

                                Kirigami.Heading {
                                    Layout.alignment: Qt.AlignHCenter
                                    level: 1
                                    text: "Welcome to Xero Wallpapers"
                                    color: "white"
                                }
                            }
                        }

                        QQC2.Label {
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            color: Kirigami.Theme.disabledTextColor
                            text: "Let's get a few things ready. It takes less than a minute."
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.largeSpacing

                            Repeater {
                                model: [
                                    { icon: "preferences-desktop-wallpaper", title: "Browse & download", text: "Wallhaven, 4K Wallpapers and your own sources" },
                                    { icon: "video-x-generic", title: "Live wallpapers", text: "Animated video wallpapers for Plasma" },
                                    { icon: "transform-crop", title: "Crop & upscale", text: "Fit any image to your screen" }
                                ]

                                delegate: Tile {
                                    required property var modelData

                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.preferredWidth: 1
                                    implicitHeight: tileCol.implicitHeight + Kirigami.Units.gridUnit * 1.5

                                    ColumnLayout {
                                        id: tileCol

                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.margins: Kirigami.Units.gridUnit * 0.75
                                        spacing: Kirigami.Units.smallSpacing

                                        Kirigami.Icon {
                                            source: modelData.icon
                                            implicitWidth: Kirigami.Units.iconSizes.medium
                                            implicitHeight: implicitWidth
                                        }

                                        QQC2.Label {
                                            Layout.fillWidth: true
                                            text: modelData.title
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideRight
                                        }

                                        QQC2.Label {
                                            Layout.fillWidth: true
                                            text: modelData.text
                                            wrapMode: Text.WordWrap
                                            color: Kirigami.Theme.disabledTextColor
                                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: aiRow.implicitHeight + Kirigami.Units.largeSpacing * 2
                            radius: Kirigami.Units.cornerRadius * 2
                            color: Qt.alpha(Kirigami.Theme.highlightColor, 0.08)
                            border.width: 1
                            border.color: Qt.alpha(Kirigami.Theme.highlightColor, 0.3)

                            RowLayout {
                                id: aiRow

                                anchors.fill: parent
                                anchors.margins: Kirigami.Units.largeSpacing
                                spacing: Kirigami.Units.largeSpacing

                                Kirigami.Icon {
                                    source: "dialog-information"
                                    implicitWidth: Kirigami.Units.iconSizes.smallMedium
                                    implicitHeight: implicitWidth
                                }

                                QQC2.Label {
                                    Layout.fillWidth: true
                                    wrapMode: Text.WordWrap
                                    font.pointSize: Kirigami.Theme.smallFont.pointSize
                                    text: "<b>Built with AI help.</b> This app was built with the help of AI coding tools. It's open source, so you can read every line on GitHub."
                                }
                            }
                        }
                    }

                    WizardPage {
                        index: 1

                        PageHeader {
                            icon: "folder-pictures"
                            title: "Wallpapers folder"
                            subtitle: "Where downloaded wallpapers are saved."
                        }

                        FolderCard {
                            kind: "static"
                            path: wizard.staticDir
                            icon: "folder-pictures"
                        }

                        QQC2.Label {
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                            color: Kirigami.Theme.disabledTextColor
                            text: "The Library shows everything in this folder, and edited copies are saved next to their originals. You can change it later in Settings."
                        }
                    }

                    WizardPage {
                        index: 2

                        PageHeader {
                            icon: "video-x-generic"
                            title: "Live wallpapers"
                            subtitle: "Animated video wallpapers need a Plasma plugin."
                        }

                        Tile {
                            Layout.fillWidth: true
                            implicitHeight: statusRow.implicitHeight + Kirigami.Units.gridUnit * 1.5

                            RowLayout {
                                id: statusRow

                                anchors.fill: parent
                                anchors.leftMargin: Kirigami.Units.gridUnit
                                anchors.rightMargin: Kirigami.Units.gridUnit
                                spacing: Kirigami.Units.gridUnit

                                Kirigami.Icon {
                                    source: "preferences-plugin"
                                    implicitWidth: Kirigami.Units.iconSizes.large
                                    implicitHeight: implicitWidth
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: Kirigami.Units.smallSpacing

                                    RowLayout {
                                        spacing: Kirigami.Units.largeSpacing

                                        QQC2.Label {
                                            text: "Smart Video Wallpaper Reborn"
                                            font.weight: Font.Bold
                                        }

                                        Pill {
                                            text: svwr.installed ? "Installed" : svwr.running ? "Installing" : "Not installed"
                                            color: svwr.installed ? Kirigami.Theme.positiveBackgroundColor
                                                : svwr.error !== "" ? Kirigami.Theme.negativeBackgroundColor
                                                : Kirigami.Theme.neutralBackgroundColor
                                            textColor: svwr.installed ? Kirigami.Theme.positiveTextColor
                                                : svwr.error !== "" ? Kirigami.Theme.negativeTextColor
                                                : Kirigami.Theme.neutralTextColor
                                        }
                                    }

                                    QQC2.Label {
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                        color: Kirigami.Theme.disabledTextColor
                                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                                        text: svwr.running ? svwr.stage
                                            : svwr.error !== "" ? svwr.error.split("\n").pop()
                                            : svwr.installed ? "Version " + svwr.version + " · ready to use"
                                            : "Plasma plugin by luisbocanegra, installed from its verified release"
                                    }

                                    QQC2.ProgressBar {
                                        Layout.fillWidth: true
                                        visible: svwr.running
                                        from: 0
                                        to: 1
                                        value: svwr.progress
                                    }
                                }

                                QQC2.Button {
                                    visible: !svwr.installed && !svwr.running
                                    text: svwr.error !== "" ? "Try again" : "Install"
                                    icon.name: "download"
                                    highlighted: true
                                    onClicked: repoPrompt.startInstall()
                                }
                            }
                        }

                        OptionCard {
                            enabled: svwr.installed && !svwr.running
                            icon: "preferences-desktop-wallpaper"
                            title: "Enable live wallpapers"
                            description: svwr.installed ? "Adds the Live tab, live sources and the live folder" : "Install the plugin first"

                            QQC2.Switch {
                                checked: wizard.liveEnabled && svwr.installed
                                onToggled: wizard.liveEnabled = checked
                            }
                        }

                        FolderCard {
                            enabled: wizard.liveEnabled && svwr.installed
                            kind: "live"
                            path: wizard.liveDir
                            icon: "folder-videos"
                        }

                        QQC2.Button {
                            Layout.alignment: Qt.AlignRight
                            flat: true
                            text: "Skip for now"
                            onClicked: {
                                wizard.liveEnabled = false
                                wizard.step += 1
                            }
                        }
                    }

                    WizardPage {
                        index: 3

                        PageHeader {
                            icon: "preferences-system"
                            title: "Preferences"
                            subtitle: "Sensible defaults. You can change any of these later in Settings."
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing * 2

                            OptionCard {
                                icon: "security-high"
                                title: "Safe content only"
                                description: "Off also shows sketchy Wallhaven images. NSFW is never shown."

                                QQC2.Switch {
                                    checked: wizard.safeContent
                                    onToggled: wizard.safeContent = checked
                                }
                            }

                            OptionCard {
                                icon: "preferences-desktop-display"
                                title: "Match my screen"
                                description: "Start with wallpapers that exactly match your screen's resolution"

                                QQC2.Switch {
                                    checked: wizard.matchScreen
                                    onToggled: wizard.matchScreen = checked
                                }
                            }

                            OptionCard {
                                icon: "edit-copy"
                                title: "Skip duplicates"
                                description: "Don't download a wallpaper that's already in the folder"

                                QQC2.Switch {
                                    checked: wizard.skipDuplicates
                                    onToggled: wizard.skipDuplicates = checked
                                }
                            }

                            OptionCard {
                                icon: "image-x-generic"
                                title: "Thumbnail cache"
                                description: wizard.clearing ? "Clearing…" : wizard.freed !== "" ? "Freed " + wizard.freed
                                    : "Older thumbnails are removed when it's full"

                                QQC2.Button {
                                    flat: true
                                    text: "Clear cache"
                                    enabled: !wizard.clearing
                                    onClicked: {
                                        wizard.clearing = true
                                        wizard.freed = ""
                                        settings.clearCache()
                                    }
                                }

                                App.CacheSizeBox {
                                    value: wizard.cacheSizeMb
                                    onPicked: size => wizard.cacheSizeMb = size
                                }
                            }
                        }
                    }

                    WizardPage {
                        index: 4

                        Kirigami.Icon {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.preferredWidth: 64
                            Layout.preferredHeight: 64
                            source: "data-success"
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: -Kirigami.Units.largeSpacing
                            spacing: Kirigami.Units.smallSpacing

                            Kirigami.Heading {
                                Layout.fillWidth: true
                                horizontalAlignment: Text.AlignHCenter
                                level: 1
                                text: "You're all set"
                            }

                            QQC2.Label {
                                Layout.fillWidth: true
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap
                                color: Kirigami.Theme.disabledTextColor
                                text: "Here's what you chose. Everything can be changed in Settings."
                            }
                        }

                        Tile {
                            Layout.fillWidth: true
                            Layout.maximumWidth: Kirigami.Units.gridUnit * 28
                            Layout.alignment: Qt.AlignHCenter
                            implicitHeight: summary.implicitHeight + Kirigami.Units.gridUnit * 1.5

                            ColumnLayout {
                                id: summary

                                anchors.fill: parent
                                anchors.margins: Kirigami.Units.gridUnit * 0.75
                                spacing: Kirigami.Units.largeSpacing

                                SummaryRow { icon: "folder-pictures"; label: "Wallpapers folder"; value: wizard.staticDir }
                                SummaryRow {
                                    icon: "video-x-generic"
                                    label: "Live wallpapers"
                                    value: wizard.liveEnabled && svwr.installed ? "On · " + wizard.liveDir : "Off"
                                }
                                SummaryRow { icon: "security-high"; label: "Safe content only"; value: wizard.safeContent ? "On" : "Off" }
                                SummaryRow { icon: "preferences-desktop-display"; label: "Match my screen"; value: wizard.matchScreen ? "On" : "Off" }
                                SummaryRow { icon: "edit-copy"; label: "Skip duplicates"; value: wizard.skipDuplicates ? "On" : "Off" }
                                SummaryRow { icon: "image-x-generic"; label: "Thumbnail cache"; value: wizard.cacheLabel(wizard.cacheSizeMb) }
                            }
                        }
                    }
                }

                Kirigami.Separator {
                    Layout.fillWidth: true
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.margins: Kirigami.Units.largeSpacing * 2
                    Layout.leftMargin: Kirigami.Units.gridUnit * 2
                    Layout.rightMargin: Kirigami.Units.gridUnit * 2
                    spacing: Kirigami.Units.largeSpacing

                    QQC2.Button {
                        flat: true
                        text: "Skip setup"
                        visible: wizard.step < wizard.lastStep
                        onClicked: wizard.close()
                    }

                    Item { Layout.fillWidth: true }

                    QQC2.Label {
                        text: "Step " + (wizard.step + 1) + " of " + wizard.steps.length
                        color: Kirigami.Theme.disabledTextColor
                    }

                    QQC2.Button {
                        flat: true
                        text: "Back"
                        icon.name: "go-previous"
                        enabled: wizard.step > 0
                        onClicked: wizard.step -= 1
                    }

                    QQC2.Button {
                        text: wizard.step === wizard.lastStep ? "Start browsing" : "Next"
                        icon.name: wizard.step === wizard.lastStep ? "dialog-ok-apply" : "go-next"
                        highlighted: true
                        onClicked: wizard.next()
                    }
                }
            }
        }
    }
}
