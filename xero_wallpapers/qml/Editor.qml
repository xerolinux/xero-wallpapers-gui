import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Rectangle {
    id: page

    readonly property var ratios: ["Original", "16:9", "16:10", "21:9", "32:9", "9:16"]
    readonly property var presets: [
        { w: 1920, h: 1080, label: "FHD" },
        { w: 2560, h: 1440, label: "QHD" },
        { w: 3440, h: 1440, label: "UW-QHD" },
        { w: 3840, h: 2160, label: "4K UHD" },
        { w: 5120, h: 2160, label: "5K2K" },
        { w: 7680, h: 4320, label: "8K" },
        { w: 0, h: 0, label: "Custom" }
    ]
    readonly property var methods: [
        { key: "lanczos", label: "Lanczos" },
        { key: "esrgan", label: "Real-ESRGAN" },
        { key: "anime", label: "Anime" }
    ]
    readonly property var crop: editor.cropRect
    readonly property real aspect: {
        if (editor.ratio === "Original")
            return editor.srcH > 0 ? editor.srcW / editor.srcH : 1
        const p = editor.ratio.split(":")
        return Number(p[0]) / Number(p[1])
    }
    property bool customPicked: false

    signal closeRequested()

    function presetIndex() {
        if (customPicked)
            return presets.length - 1
        const i = presets.findIndex(p => p.w === editor.outW && p.h === editor.outH)
        return i >= 0 ? i : presets.length - 1
    }

    function dims(w, h) {
        return w + " × " + h
    }

    color: Kirigami.Theme.backgroundColor

    onVisibleChanged: if (visible) customPicked = false

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        hoverEnabled: true
        onWheel: wheel => wheel.accepted = true
    }

    Shortcut {
        sequence: "Escape"
        enabled: page.visible && !editor.running && !confirm.visible
        onActivated: page.closeRequested()
    }

    Connections {
        target: editor

        function onDownloadConfirm() {
            confirm.open()
        }
    }

    Kirigami.PromptDialog {
        id: confirm

        property bool answered: false

        title: "Download Real-ESRGAN?"
        subtitle: "The AI upscaler is a separate 47 MB download (Real-ESRGAN v0.2.5.0 from github.com/xinntao/Real-ESRGAN). "
                  + "It is checked against a pinned SHA-256 before it runs and is kept in ~/.local/share/xero-wallpapers/realesrgan."
        standardButtons: Kirigami.Dialog.NoButton
        onOpened: answered = false
        onClosed: if (!answered) editor.confirmDownload(false)
        customFooterActions: [
            Kirigami.Action {
                text: "Download"
                icon.name: "download"
                onTriggered: {
                    confirm.answered = true
                    editor.confirmDownload(true)
                    confirm.close()
                }
            },
            Kirigami.Action {
                text: "Cancel"
                icon.name: "dialog-cancel"
                onTriggered: confirm.close()
            }
        ]
    }

    component SectionLabel: QQC2.Label {
        Layout.topMargin: Kirigami.Units.largeSpacing
        color: Kirigami.Theme.disabledTextColor
        font.capitalization: Font.AllUppercase
        font.letterSpacing: 1.2
        font.pointSize: Kirigami.Theme.smallFont.pointSize
        font.weight: Font.DemiBold
    }

    component Handle: MouseArea {
        id: handle

        required property int corner

        property point start
        property var startCrop

        width: 28
        height: 28
        x: (corner % 2 ? box.width : 0) - width / 2
        y: (corner >= 2 ? box.height : 0) - height / 2
        cursorShape: corner === 0 || corner === 3 ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor
        enabled: !editor.running
        preventStealing: true

        onPressed: mouse => {
            start = mapToItem(picture, mouse.x, mouse.y)
            startCrop = page.crop
        }
        onPositionChanged: mouse => {
            const p = mapToItem(picture, mouse.x, mouse.y)
            const s = startCrop
            const right = corner % 2 === 1
            const bottom = corner >= 2
            const anchorX = right ? s.x : s.x + s.w
            const anchorY = bottom ? s.y : s.y + s.h
            const dx = (p.x - start.x) / picture.k
            let w = Math.max(32, s.w + (right ? dx : -dx))
            const maxW = right ? editor.srcW - anchorX : anchorX
            const maxH = bottom ? editor.srcH - anchorY : anchorY
            w = Math.min(w, maxW, maxH * page.aspect)
            const h = Math.round(w / page.aspect)
            w = Math.round(w)
            editor.setCrop(right ? anchorX : anchorX - w, bottom ? anchorY : anchorY - h, w, h)
        }

        Rectangle {
            x: handle.corner % 2 ? handle.width / 2 - width : handle.width / 2 - 3
            y: handle.corner >= 2 ? handle.height / 2 - height : handle.height / 2 - 3
            width: 16
            height: 3
            color: "white"
        }

        Rectangle {
            x: handle.corner % 2 ? handle.width / 2 - 3 : handle.width / 2 - 3
            y: handle.corner >= 2 ? handle.height / 2 - height : handle.height / 2 - 3
            width: 3
            height: 16
            color: "white"
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            Layout.leftMargin: 18
            Layout.rightMargin: 18
            spacing: Kirigami.Units.largeSpacing

            QQC2.ToolButton {
                icon.name: "go-previous"
                text: "Back"
                display: QQC2.AbstractButton.IconOnly
                enabled: !editor.running
                onClicked: page.closeRequested()
                QQC2.ToolTip.text: text
                QQC2.ToolTip.visible: hovered
                QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
            }

            Kirigami.Heading {
                text: "Crop & Upscale"
                level: 3
            }

            QQC2.Label {
                Layout.fillWidth: true
                text: editor.fileName ? editor.fileName + " · " + page.dims(editor.srcW, editor.srcH) : ""
                color: Kirigami.Theme.disabledTextColor
                elide: Text.ElideMiddle
            }

            QQC2.Button {
                text: "Reset"
                flat: true
                enabled: !editor.running && editor.srcW > 0
                onClicked: {
                    page.customPicked = false
                    editor.setRatio("Original")
                    editor.setOutput(editor.srcW, editor.srcH)
                }
            }
        }

        Kirigami.Separator { Layout.fillWidth: true }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                id: canvas

                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Kirigami.Theme.alternateBackgroundColor
                clip: true

                Item {
                    id: picture

                    readonly property real k: editor.srcW > 0
                        ? Math.min((canvas.width - 64) / editor.srcW, (canvas.height - 72) / editor.srcH) : 0

                    anchors.centerIn: parent
                    anchors.verticalCenterOffset: -8
                    width: Math.round(editor.srcW * k)
                    height: Math.round(editor.srcH * k)

                    Image {
                        id: image

                        anchors.fill: parent
                        source: page.visible ? editor.sourceUrl : ""
                        sourceSize: Qt.size(Math.round(parent.width * Screen.devicePixelRatio),
                                            Math.round(parent.height * Screen.devicePixelRatio))
                        fillMode: Image.Stretch
                        asynchronous: true
                        cache: false
                    }

                    QQC2.BusyIndicator {
                        anchors.centerIn: parent
                        running: image.status === Image.Loading
                        visible: running
                    }

                    Rectangle {
                        x: 0; y: 0; width: parent.width; height: box.y
                        color: "black"; opacity: 0.58
                    }
                    Rectangle {
                        x: 0; y: box.y + box.height; width: parent.width; height: parent.height - y
                        color: "black"; opacity: 0.58
                    }
                    Rectangle {
                        x: 0; y: box.y; width: box.x; height: box.height
                        color: "black"; opacity: 0.58
                    }
                    Rectangle {
                        x: box.x + box.width; y: box.y; width: parent.width - x; height: box.height
                        color: "black"; opacity: 0.58
                    }

                    Item {
                        id: box

                        x: page.crop.x * picture.k
                        y: page.crop.y * picture.k
                        width: page.crop.w * picture.k
                        height: page.crop.h * picture.k

                        Rectangle {
                            anchors.fill: parent
                            color: "transparent"
                            border.width: 2
                            border.color: "white"
                        }

                        Repeater {
                            model: 2

                            delegate: Item {
                                required property int index

                                Rectangle {
                                    x: box.width * (parent.index + 1) / 3
                                    width: 1
                                    height: box.height
                                    color: "white"
                                    opacity: 0.35
                                }

                                Rectangle {
                                    y: box.height * (parent.index + 1) / 3
                                    width: box.width
                                    height: 1
                                    color: "white"
                                    opacity: 0.35
                                }
                            }
                        }

                        MouseArea {
                            property point start
                            property var startCrop

                            anchors.fill: parent
                            cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                            enabled: !editor.running
                            preventStealing: true
                            onPressed: mouse => {
                                start = mapToItem(picture, mouse.x, mouse.y)
                                startCrop = page.crop
                            }
                            onPositionChanged: mouse => {
                                const p = mapToItem(picture, mouse.x, mouse.y)
                                editor.setCrop(Math.round(startCrop.x + (p.x - start.x) / picture.k),
                                               Math.round(startCrop.y + (p.y - start.y) / picture.k),
                                               startCrop.w, startCrop.h)
                            }
                        }

                        Rectangle {
                            anchors.centerIn: parent
                            width: sizeLabel.implicitWidth + 20
                            height: sizeLabel.implicitHeight + 8
                            radius: 6
                            color: "black"
                            opacity: 0.6
                            visible: editor.srcW > 0
                        }

                        QQC2.Label {
                            id: sizeLabel

                            anchors.centerIn: parent
                            text: page.dims(page.crop.w, page.crop.h)
                            color: "white"
                            font.weight: Font.DemiBold
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            visible: editor.srcW > 0
                        }

                        Repeater {
                            model: 4

                            delegate: Handle {
                                required property int index

                                corner: index
                            }
                        }
                    }
                }

                RowLayout {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 14
                    spacing: Kirigami.Units.smallSpacing
                    visible: editor.srcW > 0

                    Kirigami.Icon {
                        source: "zoom-fit-best"
                        implicitWidth: Kirigami.Units.iconSizes.small
                        implicitHeight: implicitWidth
                        opacity: 0.6
                    }

                    QQC2.Label {
                        text: "Fit · " + Math.round(picture.k * 100) + "%"
                        color: Kirigami.Theme.disabledTextColor
                        font.pointSize: Kirigami.Theme.smallFont.pointSize
                    }
                }
            }

            Kirigami.Separator { Layout.fillHeight: true }

            QQC2.ScrollView {
                id: panelScroll

                Layout.preferredWidth: 350
                Layout.fillHeight: true
                contentWidth: availableWidth

                ColumnLayout {
                    width: panelScroll.availableWidth
                    spacing: Kirigami.Units.smallSpacing

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 18
                        Layout.leftMargin: 18
                        Layout.rightMargin: 18
                        spacing: Kirigami.Units.smallSpacing
                        enabled: !editor.running

                        SectionLabel { text: "Aspect ratio"; Layout.topMargin: 0 }

                        Flow {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            Repeater {
                                model: page.ratios

                                delegate: Kirigami.Chip {
                                    required property string modelData

                                    text: modelData
                                    checkable: true
                                    closable: false
                                    checked: editor.ratio === modelData
                                    onClicked: editor.setRatio(modelData)
                                }
                            }
                        }

                        SectionLabel { text: "Output resolution" }

                        QQC2.ComboBox {
                            id: resolution

                            Layout.fillWidth: true
                            model: page.presets
                            textRole: "label"
                            currentIndex: page.presetIndex()
                            displayText: {
                                const p = page.presets[currentIndex]
                                return p && p.w ? page.dims(p.w, p.h) + "   " + p.label : "Custom · " + page.dims(editor.outW, editor.outH)
                            }
                            delegate: QQC2.ItemDelegate {
                                required property var modelData
                                required property int index

                                width: resolution.width
                                highlighted: resolution.highlightedIndex === index
                                contentItem: RowLayout {
                                    QQC2.Label {
                                        Layout.fillWidth: true
                                        text: modelData.w ? page.dims(modelData.w, modelData.h) : "Custom"
                                    }
                                    QQC2.Label {
                                        text: modelData.w ? modelData.label : ""
                                        color: Kirigami.Theme.disabledTextColor
                                    }
                                }
                            }
                            onActivated: index => {
                                const p = page.presets[index]
                                page.customPicked = !p.w
                                if (p.w)
                                    editor.setOutput(p.w, p.h)
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            visible: resolution.currentIndex === page.presets.length - 1

                            QQC2.SpinBox {
                                Layout.fillWidth: true
                                from: 1
                                to: 16384
                                editable: true
                                value: editor.outW
                                onValueModified: editor.setOutput(value, editor.outH)
                            }

                            QQC2.Label { text: "×" }

                            QQC2.SpinBox {
                                Layout.fillWidth: true
                                from: 1
                                to: 16384
                                editable: true
                                value: editor.outH
                                onValueModified: editor.setOutput(editor.outW, value)
                            }
                        }

                        SectionLabel { text: "Upscaler" }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 0

                            Repeater {
                                model: page.methods

                                delegate: QQC2.Button {
                                    required property var modelData

                                    Layout.fillWidth: true
                                    text: modelData.label
                                    checkable: true
                                    checked: editor.method === modelData.key
                                    enabled: modelData.key === "lanczos" || editor.aiAvailable
                                    onClicked: editor.setMethod(modelData.key)
                                }
                            }
                        }

                        QQC2.Label {
                            Layout.fillWidth: true
                            visible: !editor.aiAvailable
                            text: "Real-ESRGAN: " + editor.aiUnavailableReason
                            color: Kirigami.Theme.neutralTextColor
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            wrapMode: Text.WordWrap
                        }

                        QQC2.Label {
                            Layout.fillWidth: true
                            text: editor.hint
                            color: Kirigami.Theme.disabledTextColor
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            wrapMode: Text.WordWrap
                        }

                        SectionLabel { text: "Detail" }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: Kirigami.Units.largeSpacing

                            QQC2.Label {
                                text: "Denoise"
                                opacity: editor.method === "lanczos" ? 1 : 0.5
                            }
                            QQC2.Slider {
                                Layout.fillWidth: true
                                from: 0
                                to: 1
                                value: editor.denoise
                                enabled: editor.method === "lanczos"
                                onMoved: editor.denoise = value
                                QQC2.ToolTip.text: "Real-ESRGAN denoises on its own"
                                QQC2.ToolTip.visible: hovered && !enabled
                            }

                            QQC2.Label { text: "Sharpen" }
                            QQC2.Slider {
                                Layout.fillWidth: true
                                from: 0
                                to: 1
                                value: editor.sharpen
                                onMoved: editor.sharpen = value
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 18
                        Layout.rightMargin: 18
                        Layout.bottomMargin: 18
                        spacing: Kirigami.Units.smallSpacing

                        SectionLabel { text: "Summary" }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: Kirigami.Units.largeSpacing

                            Repeater {
                                model: [
                                    ["Source", editor.summary.source],
                                    ["Crop", editor.summary.crop],
                                    ["Output", editor.summary.output],
                                    ["Scale", editor.summary.scale]
                                ]

                                delegate: RowLayout {
                                    required property var modelData
                                    required property int index

                                    Layout.columnSpan: 2
                                    Layout.fillWidth: true

                                    QQC2.Label {
                                        Layout.fillWidth: true
                                        text: modelData[0]
                                        color: Kirigami.Theme.disabledTextColor
                                    }
                                    QQC2.Label {
                                        text: modelData[1] || ""
                                        font.weight: Font.DemiBold
                                        color: index === 3 ? Kirigami.Theme.highlightColor : Kirigami.Theme.textColor
                                    }
                                }
                            }
                        }

                        QQC2.Label {
                            Layout.fillWidth: true
                            visible: text !== ""
                            text: editor.summary.note || ""
                            color: Kirigami.Theme.disabledTextColor
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            wrapMode: Text.WordWrap
                        }

                        QQC2.Label {
                            Layout.topMargin: Kirigami.Units.largeSpacing
                            Layout.fillWidth: true
                            visible: editor.stage !== ""
                            text: editor.stage
                            color: editor.stage.startsWith("Failed") ? Kirigami.Theme.negativeTextColor
                                                                     : Kirigami.Theme.disabledTextColor
                            wrapMode: Text.WordWrap
                        }

                        // Plain bar: Breeze's ProgressBar spams TypeErrors when its width changes inside a layout.
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 6
                            visible: editor.running
                            radius: 3
                            color: Kirigami.Theme.alternateBackgroundColor

                            Rectangle {
                                width: parent.width * editor.progress
                                height: parent.height
                                radius: 3
                                color: Kirigami.Theme.highlightColor

                                Behavior on width {
                                    NumberAnimation { duration: Kirigami.Units.shortDuration }
                                }
                            }
                        }

                        QQC2.CheckBox {
                            id: setAfter

                            text: "Set as wallpaper after saving"
                            enabled: !editor.running
                        }

                        QQC2.Button {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 36
                            highlighted: !editor.running
                            enabled: editor.srcW > 0
                            icon.name: editor.running ? "dialog-cancel" : "transform-scale"
                            text: editor.running ? "Cancel" : "Upscale & Save copy"
                            onClicked: editor.running ? editor.cancel() : editor.apply(setAfter.checked)
                        }
                    }
                }
            }
        }
    }
}
