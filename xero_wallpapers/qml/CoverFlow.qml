import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Effects
import QtQuick.Layouts
import QtMultimedia
import org.kde.kirigami as Kirigami
import "." as App

Window {
    id: flow

    property url logoUrl
    property alias currentIndex: view.currentIndex
    property string toastText: ""
    property string toastIcon: ""
    property real toastProgress: -1
    property string pendingTitle: ""
    property int previewIndex: -1
    property url previewSource: ""

    signal cropRequested(int index)

    readonly property int coverWidth: 660
    readonly property int coverHeight: 371
    readonly property real perspective: 1500
    readonly property real tilt: 58
    readonly property real coverTop: Math.round(height * 0.43 - coverHeight / 2)
    // PathView doesn't always notify currentItem after its model resets, so it is also read in select().
    property var current: null
    readonly property string sourceLabel: {
        const hit = (browse.sources || []).find(s => s.name === browse.currentSource)
        return hit ? hit.label : browse.currentSource
    }

    function select(index) {
        const i = Math.max(0, Math.min(index, view.count - 1))
        view.currentIndex = i
        view.positionViewAtIndex(i, PathView.Center)
        current = view.currentItem
        view.forceActiveFocus()
        maybeLoadMore()
    }

    function openAt(index) {
        // The view only creates its covers once the window is shown.
        showFullScreen()
        select(index)
        requestActivate()
    }

    function step(delta) {
        const i = view.currentIndex + delta
        if (i >= 0 && i < view.count)
            view.currentIndex = i
    }

    function maybeLoadMore() {
        if (visible && view.count > 0 && view.currentIndex >= view.count - 4)
            browse.loadMore()
    }

    function setCurrent() {
        if (!current || pendingTitle !== "")
            return
        // Matches DownloadController's signal title, which falls back to the source label.
        pendingTitle = current.title || current.source
        toast("download", "Downloading " + pendingTitle, 0)
        stallTimer.restart()
        downloads.download(view.currentIndex, true)
    }

    function settle(icon, text) {
        pendingTitle = ""
        stallTimer.stop()
        toast(icon, text, -1)
    }

    // CSS-style tilt: rotateY about the cover centre, translate, then perspective about the screen centre.
    // Rows are flattened to z = 0 so the scene graph only sees the projected (x, y, w).
    function coverMatrix(tx, tz, degrees) {
        const r = degrees * Math.PI / 180
        const c = Math.cos(r), s = Math.sin(r), d = perspective
        const w = coverWidth, h = coverHeight
        const ax = w / 2, ay = height / 2 - coverTop
        const oy = coverTop + h / 2 - height / 2
        const w0 = 1 - s * w / (2 * d) - tz / d
        return Qt.matrix4x4(c + ax * s / d, 0, 0, -c * w / 2 + tx + ax * w0,
                            ay * s / d, 1, 0, -h / 2 + oy + ay * w0,
                            0, 0, 1, 0,
                            s / d, 0, 0, w0)
    }

    function stopPreview() {
        previewIndex = -1
        previewSource = ""
    }

    function toggleInfo() {
        if (sheet.visible)
            sheet.close()
        else if (view.count > 0)
            sheet.show(view.currentIndex)
    }

    function toast(icon, text, progress) {
        toastIcon = icon
        toastText = text
        toastProgress = progress
        if (progress < 0)
            toastTimer.restart()
        else
            toastTimer.stop()
    }

    title: "Xero Wallpapers"
    color: "black"
    onVisibleChanged: {
        if (!visible) {
            stopPreview()
            sheet.close()
            pendingTitle = ""
            stallTimer.stop()
            toastTimer.stop()
            toastText = ""
            toastIcon = ""
            toastProgress = -1
        }
        maybeLoadMore()
    }

    Connections {
        target: downloads

        function onProgress(title, done, total) {
            if (title !== flow.pendingTitle)
                return
            stallTimer.restart()
            flow.toast("download", "Downloading " + title, total > 0 ? done / total : 0)
        }

        function onFinished(title, path, wasSet, existing) {
            if (title === flow.pendingTitle)
                flow.settle("preferences-desktop-wallpaper",
                            (existing ? "Already in your Library · " : "") + title + " set as your wallpaper")
        }

        function onFailed(title, message) {
            // An empty title means the controller rejected the request before it knew the item.
            if (flow.pendingTitle !== "" && (title === flow.pendingTitle || title === ""))
                flow.settle("dialog-error", "Couldn't set " + flow.pendingTitle + ": " + message)
        }
    }

    Timer {
        id: stallTimer
        interval: 60000
        onTriggered: flow.settle("dialog-error", "Couldn't set " + flow.pendingTitle + ": no response")
    }

    Timer {
        id: toastTimer
        interval: 3000
        onTriggered: flow.toastText = ""
    }

    // Only the settled centre cover of a live wallpaper plays, and only one video at a time.
    Timer {
        interval: 300
        running: flow.visible && flow.current !== null && flow.current.kind === "live"
                 && flow.previewIndex !== view.currentIndex && Math.abs(view.centre - view.currentIndex) < 0.01
        onTriggered: detail.requestPreview(view.currentIndex)
    }

    Connections {
        target: detail

        function onPreviewReady(index, url) {
            if (flow.visible && index === view.currentIndex) {
                flow.previewIndex = index
                flow.previewSource = url
            }
        }
    }

    Item {
        id: backdrop

        property string wanted: flow.current ? flow.current.thumb : ""
        property bool frontIsA: true

        function swap() {
            const back = frontIsA ? bgB : bgA
            const front = frontIsA ? bgA : bgB
            if (front.source.toString() === wanted)
                return
            back.source = wanted
            if (back.status === Image.Ready)
                frontIsA = !frontIsA
        }

        anchors.fill: parent
        anchors.margins: -80
        visible: false
        onWantedChanged: backdropTimer.restart()

        Timer {
            id: backdropTimer
            interval: 150
            onTriggered: backdrop.swap()
        }

        component Backdrop: Image {
            property bool front

            anchors.fill: parent
            fillMode: Image.PreserveAspectCrop
            sourceSize.width: 480
            asynchronous: true
            opacity: front ? 1 : 0
            onStatusChanged: {
                if (status === Image.Ready && !front && source.toString() === backdrop.wanted)
                    backdrop.frontIsA = !backdrop.frontIsA
            }

            Behavior on opacity {
                NumberAnimation { duration: 600 }
            }
        }

        Backdrop { id: bgA; front: backdrop.frontIsA }
        Backdrop { id: bgB; front: !backdrop.frontIsA }
    }

    MultiEffect {
        anchors.fill: backdrop
        source: backdrop
        blurEnabled: true
        blur: 1
        blurMax: 64
        saturation: 0.4
        brightness: -0.35
    }

    Rectangle {
        anchors.fill: parent
        color: "#59000000"
    }

    PathView {
        id: view

        readonly property real centre: {
            const c = count - offset
            return c > count - 0.5 ? c - count : c
        }

        anchors.fill: parent
        model: browse.model
        focus: true
        interactive: false
        pathItemCount: 9
        cacheItemCount: 4
        preferredHighlightBegin: 0.5
        preferredHighlightEnd: 0.5
        highlightRangeMode: PathView.StrictlyEnforceRange
        highlightMoveDuration: 600
        snapMode: PathView.SnapOneItem
        path: Path {
            startX: 0
            startY: view.height / 2

            PathLine {
                x: view.width
                y: view.height / 2
            }
        }

        onCurrentItemChanged: flow.current = currentItem
        onCurrentIndexChanged: {
            flow.stopPreview()
            flow.maybeLoadMore()
        }
        onCountChanged: flow.maybeLoadMore()

        Keys.onPressed: event => {
            switch (event.key) {
            case Qt.Key_Left:
                flow.step(-1)
                break
            case Qt.Key_Right:
                flow.step(1)
                break
            case Qt.Key_Space:
                if (!event.isAutoRepeat)
                    flow.setCurrent()
                break
            case Qt.Key_I:
                flow.toggleInfo()
                break
            case Qt.Key_Escape:
                if (sheet.visible)
                    sheet.close()
                else
                    flow.close()
                break
            default:
                return
            }
            event.accepted = true
        }

        WheelHandler {
            id: wheel

            property real pending: 0

            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            onWheel: event => {
                const touch = event.pixelDelta.x !== 0 || event.pixelDelta.y !== 0
                const dx = touch ? event.pixelDelta.x : event.angleDelta.x
                const dy = touch ? event.pixelDelta.y : event.angleDelta.y
                if (!touch && Math.abs(dx) > Math.abs(dy))
                    return
                const threshold = touch ? 200 : 120
                pending += Math.abs(dy) >= Math.abs(dx) ? dy : dx
                wheelIdle.restart()
                while (Math.abs(pending) >= threshold) {
                    flow.step(pending > 0 ? -1 : 1)
                    pending -= Math.sign(pending) * threshold
                }
            }
        }

        Timer {
            id: wheelIdle
            interval: 200
            onTriggered: wheel.pending = 0
        }

        delegate: Item {
            id: card

            required property int index
            required property string title
            required property string thumb
            required property string cover
            required property string resolution
            required property string source
            required property string author
            required property string fill
            required property string kind

            readonly property real d: index - view.centre
            readonly property real a: Math.abs(d)
            readonly property real t: Math.min(a, 1)
            readonly property int side: d < 0 ? -1 : 1
            readonly property real offsetX: side * (a < 1 ? 380 * t : 250 + 130 * a)
            readonly property real depth: a < 1 ? 80 - 200 * t : -120 * a
            property bool heroWanted: false

            width: 0
            height: 0
            z: 100 - a
            opacity: Math.max(0, Math.min(1, 4 - a))
            visible: opacity > 0
            onAChanged: if (a > 1.5) heroWanted = false

            Timer {
                interval: 300
                running: card.a < 0.01 && !card.heroWanted && flow.visible
                onTriggered: card.heroWanted = true
            }

            Item {
                id: body

                x: (flow.width - flow.coverWidth) / 2 - card.x
                y: flow.coverTop - card.y
                width: flow.coverWidth
                height: flow.coverHeight

                transform: Matrix4x4 {
                    matrix: flow.coverMatrix(card.offsetX, card.depth, -card.side * card.t * flow.tilt)
                }

                TapHandler {
                    onTapped: card.index === view.currentIndex ? flow.toggleInfo() : view.currentIndex = card.index
                }

                Kirigami.ShadowedRectangle {
                    anchors.fill: parent
                    radius: Kirigami.Units.cornerRadius * 2
                    color: Kirigami.Theme.alternateBackgroundColor
                    shadow.size: 60
                    shadow.yOffset: 30
                    shadow.color: Qt.rgba(0, 0, 0, 0.6)
                }

                Item {
                    id: face

                    anchors.fill: parent

                    App.FitImage {
                        anchors.fill: parent
                        radius: Kirigami.Units.cornerRadius * 2
                        source: card.visible ? card.thumb : ""
                        fillSource: card.visible ? card.fill : ""
                        sourceSize.width: Math.round(flow.coverWidth * Screen.devicePixelRatio)
                    }

                    App.FitImage {
                        id: hero

                        anchors.fill: parent
                        radius: Kirigami.Units.cornerRadius * 2
                        source: card.heroWanted ? card.cover : ""
                        sourceSize.width: Math.round(flow.coverWidth * 1.06 * Screen.devicePixelRatio)
                        opacity: status === Image.Ready ? 1 : 0

                        Behavior on opacity {
                            NumberAnimation { duration: Kirigami.Units.longDuration }
                        }
                    }

                    Loader {
                        anchors.fill: parent
                        active: flow.previewIndex === card.index && flow.previewSource.toString() !== ""
                        sourceComponent: Video {
                            source: flow.previewSource
                            autoPlay: true
                            muted: true
                            loops: MediaPlayer.Infinite
                            fillMode: VideoOutput.PreserveAspectCrop
                            opacity: playbackState === MediaPlayer.PlayingState && position > 0 ? 1 : 0

                            Behavior on opacity {
                                NumberAnimation { duration: Kirigami.Units.longDuration }
                            }
                        }
                    }

                    Rectangle {
                        anchors.fill: parent
                        radius: Kirigami.Units.cornerRadius * 2
                        color: "black"
                        opacity: 0.35 * card.t
                    }
                }

                ShaderEffectSource {
                    id: mirror

                    visible: false
                    sourceItem: face
                    sourceRect: Qt.rect(0, face.height * 0.72, face.width, face.height * 0.28)
                    width: face.width
                    height: Math.round(face.height * 0.28)
                }

                Rectangle {
                    id: fade

                    width: mirror.width
                    height: mirror.height
                    visible: false
                    layer.enabled: true
                    gradient: Gradient {
                        GradientStop { position: 0; color: "#00ffffff" }
                        GradientStop { position: 1; color: "#ffffffff" }
                    }
                }

                MultiEffect {
                    y: face.height + 6
                    width: mirror.width
                    height: mirror.height
                    source: mirror
                    maskEnabled: true
                    maskSource: fade
                    maskThresholdMin: 0.5
                    maskSpreadAtMin: 1
                    opacity: 0.18
                    transform: Scale { origin.y: mirror.height / 2; yScale: -1 }
                }
            }
        }
    }

    RowLayout {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: 18
        anchors.leftMargin: 24
        anchors.rightMargin: 24
        spacing: Kirigami.Units.smallSpacing * 2

        Image {
            source: flow.logoUrl
            sourceSize.width: 20
            sourceSize.height: 20
        }

        QQC2.Label {
            Layout.fillWidth: true
            text: "Xero Wallpapers"
            color: "white"
            font.pixelSize: 14
            font.weight: Font.DemiBold
        }

        QQC2.Label {
            text: "3D tilt coverflow · " + view.count + " wallpapers · " + flow.sourceLabel
            color: "white"
            opacity: 0.75
            font.pixelSize: 13
        }
    }

    ColumnLayout {
        anchors.horizontalCenter: parent.horizontalCenter
        y: flow.height * 0.43 + 230
        width: Math.min(flow.coverWidth, flow.width - 48)
        spacing: 6
        visible: flow.current !== null

        QQC2.Label {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: flow.current ? (flow.current.title || flow.current.source) : ""
            color: "white"
            font.pixelSize: 26
            font.weight: Font.Bold
            elide: Text.ElideRight
        }

        QQC2.Label {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: {
                const c = flow.current
                if (!c)
                    return ""
                const parts = [c.resolution, c.title ? c.source : ""]
                if (c.author)
                    parts.push("by " + c.author)
                return parts.filter(p => p).join(" · ")
            }
            color: "white"
            opacity: 0.7
            font.pixelSize: 13
            elide: Text.ElideRight
        }
    }

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: hints.top
        anchors.bottomMargin: 18
        width: toastRow.implicitWidth + Kirigami.Units.largeSpacing * 2
        height: toastRow.implicitHeight + Kirigami.Units.largeSpacing * 2
        radius: Kirigami.Units.cornerRadius * 2
        color: Kirigami.Theme.backgroundColor
        opacity: flow.toastText !== "" ? 1 : 0
        visible: opacity > 0

        Behavior on opacity {
            NumberAnimation { duration: Kirigami.Units.longDuration }
        }

        RowLayout {
            id: toastRow

            anchors.centerIn: parent
            spacing: Kirigami.Units.largeSpacing

            Kirigami.Icon {
                source: flow.toastIcon
                Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
            }

            QQC2.Label {
                text: flow.toastText
                Layout.maximumWidth: flow.width * 0.6
                elide: Text.ElideRight
            }

            // Plain bar: Breeze's ProgressBar spams TypeErrors when its width changes inside a layout.
            Rectangle {
                Layout.preferredWidth: 140
                Layout.preferredHeight: 4
                visible: flow.toastProgress >= 0
                radius: 2
                color: Kirigami.Theme.alternateBackgroundColor

                Rectangle {
                    width: parent.width * Math.max(0, flow.toastProgress)
                    height: parent.height
                    radius: 2
                    color: Kirigami.Theme.highlightColor

                    Behavior on width {
                        NumberAnimation { duration: Kirigami.Units.shortDuration }
                    }
                }
            }
        }
    }

    component Hint: Row {
        property string keys
        property string label

        spacing: 6

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: keyLabel.implicitWidth + 14
            height: keyLabel.implicitHeight + 4
            radius: 5
            color: "transparent"
            border.color: Qt.rgba(1, 1, 1, 0.35)

            QQC2.Label {
                id: keyLabel
                anchors.centerIn: parent
                text: parent.parent.keys
                color: "white"
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
        }

        QQC2.Label {
            anchors.verticalCenter: parent.verticalCenter
            text: parent.label
            color: "white"
            opacity: 0.65
            font.pixelSize: 12
        }
    }

    Row {
        id: hints

        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 22
        spacing: 22

        Hint { keys: "← →"; label: "Browse" }
        Hint { keys: "Space"; label: "Download & set" }
        Hint { keys: "I"; label: "Info" }
        Hint { keys: "Esc"; label: "Exit" }
    }

    App.DetailSheet {
        id: sheet

        // Kirigami.Dialog defaults to the main window's overlay, which sits behind this fullscreen window.
        parent: flow.contentItem
        onClosed: view.forceActiveFocus()
        onCropRequested: index => {
            flow.close()
            flow.cropRequested(index)
        }
    }
}
