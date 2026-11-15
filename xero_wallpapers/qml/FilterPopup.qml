import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

QQC2.Popup {
    id: popup

    readonly property var hues: [0, 30, 55, 130, 180, 215, 265, 310]
    readonly property var resolutions: [["any", "Any"], ["1080p", "1080p"], ["1440p", "1440p"], ["4k", "4K+"]]
    readonly property var ratios: [["any", "Any"], ["16:9", "16:9"], ["16:10", "16:10"], ["21:9", "21:9"],
                                   ["32:9", "32:9"], ["ultrawide", "Ultra-wide"]]
    readonly property string noResolution: "This source doesn't list resolutions, so these filters don't apply"

    property var draftTags: []
    property string draftCategory: ""
    property bool draftNoAnime: false
    property int draftHue: -1
    property string draftRes: "any"
    property string draftRatio: "any"

    readonly property bool resolutionKnown: browse.filterInfo.resolution === true
    readonly property var categories: browse.filterInfo.categories || []
    readonly property var tagOptions: {
        const tags = (browse.filterInfo.tags || []).slice()
        for (const t of draftTags)
            if (tags.indexOf(t) < 0)
                tags.push(t)
        return tags
    }

    function draft() {
        // The controller drops a category No anime hides, so turning it on here needs no extra check.
        return { tags: draftTags, category: draftCategory, hue: draftHue, min_res: draftRes, ratio: draftRatio }
    }

    function toggleTag(tag) {
        const tags = draftTags.slice()
        const i = tags.indexOf(tag)
        if (i >= 0)
            tags.splice(i, 1)
        else
            tags.push(tag)
        draftTags = tags
    }

    onAboutToShow: {
        const f = browse.filters
        draftTags = (f.tags || []).slice()
        draftCategory = f.category || ""
        draftNoAnime = settings.noAnime
        draftHue = typeof f.hue === "number" ? f.hue : -1
        draftRes = f.min_res
        draftRatio = f.ratio
    }

    width: 400
    padding: Kirigami.Units.gridUnit
    modal: false
    focus: true
    closePolicy: QQC2.Popup.CloseOnEscape | QQC2.Popup.CloseOnPressOutsideParent

    background: Kirigami.ShadowedRectangle {
        radius: Kirigami.Units.cornerRadius * 2
        color: Kirigami.Theme.backgroundColor
        border.width: 1
        border.color: Qt.alpha(Kirigami.Theme.textColor, 0.15)
        shadow.size: 24
        shadow.yOffset: 8
        shadow.color: Qt.rgba(0, 0, 0, 0.35)
    }

    component Unavailable: Item {
        id: wrap

        property bool available: true
        property string reason
        default property alias content: inner.data

        implicitWidth: inner.childrenRect.width
        implicitHeight: inner.childrenRect.height

        HoverHandler { id: hover }

        QQC2.ToolTip.visible: !available && hover.hovered
        QQC2.ToolTip.text: reason

        Item {
            id: inner
            anchors.fill: parent
            enabled: wrap.available
            opacity: enabled ? 1 : 0.4
        }
    }

    component SectionLabel: QQC2.Label {
        Layout.topMargin: Kirigami.Units.smallSpacing
        font.weight: Font.DemiBold
        opacity: 0.7
    }

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing * 2

        RowLayout {
            Layout.fillWidth: true

            QQC2.Label {
                Layout.fillWidth: true
                text: "No anime"
                font.weight: Font.DemiBold
                opacity: 0.7
            }

            QQC2.Switch {
                checked: popup.draftNoAnime
                onToggled: popup.draftNoAnime = checked
            }
        }

        SectionLabel { text: popup.categories.length > 0 ? "Category" : "Tags" }

        Flow {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
            visible: popup.categories.length > 0

            Kirigami.Chip {
                text: "All"
                checkable: true
                closable: false
                checked: popup.draftCategory === ""
                onClicked: popup.draftCategory = ""
            }

            Repeater {
                model: popup.categories

                delegate: Kirigami.Chip {
                    required property var modelData
                    text: modelData.label
                    checkable: true
                    closable: false
                    checked: popup.draftCategory === modelData.slug
                    onClicked: popup.draftCategory = modelData.slug
                }
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing
            visible: popup.categories.length === 0 && popup.tagOptions.length > 0

            Repeater {
                model: popup.tagOptions

                delegate: Kirigami.Chip {
                    required property string modelData
                    text: "#" + modelData
                    checkable: true
                    closable: false
                    checked: popup.draftTags.indexOf(modelData) >= 0
                    onClicked: popup.toggleTag(modelData)
                }
            }
        }

        QQC2.Label {
            visible: popup.categories.length === 0 && popup.tagOptions.length === 0
            text: "No tags in the loaded wallpapers"
            opacity: 0.6
        }

        SectionLabel { text: "Colour" }

        RowLayout {
            spacing: Kirigami.Units.smallSpacing * 2

            Repeater {
                model: popup.hues

                delegate: QQC2.AbstractButton {
                    id: swatch

                    required property int modelData
                    readonly property bool active: popup.draftHue === modelData

                    implicitWidth: 26
                    implicitHeight: 26
                    scale: active ? 1.12 : 1
                    onClicked: popup.draftHue = active ? -1 : modelData

                    background: Rectangle {
                        radius: width / 2
                        color: Qt.hsla(swatch.modelData / 360, 0.7, 0.52, 1)
                        border.width: 2
                        border.color: swatch.active || swatch.visualFocus ? Kirigami.Theme.textColor : "transparent"
                    }

                    Behavior on scale {
                        NumberAnimation { duration: Kirigami.Units.shortDuration }
                    }

                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                }
            }
        }

        SectionLabel { text: "Resolution" }

        Unavailable {
            available: popup.resolutionKnown
            reason: popup.noResolution

            RowLayout {
                spacing: 0

                Repeater {
                    model: popup.resolutions

                    delegate: QQC2.Button {
                        required property var modelData
                        text: modelData[1]
                        checkable: true
                        checked: popup.draftRes === modelData[0]
                        onClicked: {
                            popup.draftRes = modelData[0]
                            if (modelData[0] !== "any" && popup.draftRatio === "ultrawide")
                                popup.draftRatio = "any"
                        }
                    }
                }
            }
        }

        SectionLabel { text: "Aspect ratio" }

        Unavailable {
            available: popup.resolutionKnown
            reason: popup.noResolution

            Flow {
                width: popup.availableWidth
                spacing: Kirigami.Units.smallSpacing

                Repeater {
                    model: popup.ratios

                    delegate: Kirigami.Chip {
                        required property var modelData
                        text: modelData[1]
                        checkable: true
                        closable: false
                        // Ultra-wide sizes don't follow the 16:9 resolution steps, so it needs resolution "Any".
                        enabled: modelData[0] !== "ultrawide" || popup.draftRes === "any"
                        checked: popup.draftRatio === modelData[0]
                        onClicked: popup.draftRatio = modelData[0]
                    }
                }
            }
        }

        QQC2.Label {
            Layout.fillWidth: true
            visible: !popup.resolutionKnown
            text: popup.noResolution
            wrapMode: Text.WordWrap
            font.pointSize: smallPointSize
            opacity: 0.6
        }

        RowLayout {
            Layout.topMargin: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing * 2

            Item { Layout.fillWidth: true }

            QQC2.Button {
                text: "Clear"
                flat: true
                onClicked: {
                    popup.draftTags = []
                    popup.draftCategory = ""
                    popup.draftHue = -1
                    popup.draftRes = "any"
                    popup.draftRatio = "any"
                }
            }

            QQC2.Button {
                text: "Apply filters"
                highlighted: true
                onClicked: {
                    // Set before applying so a hidden anime category is dropped in the same reload.
                    settings.noAnime = popup.draftNoAnime
                    browse.applyFilters(popup.draft())
                    popup.close()
                }
            }
        }
    }
}
