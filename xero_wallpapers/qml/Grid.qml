import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "." as App

Item {
    id: page

    property url logoUrl

    signal openDetail(int index)
    signal openCoverFlow(int index)

    readonly property int sideMargin: 26
    readonly property int gap: 18
    readonly property int minCardWidth: 230

    readonly property var sorts: [
        ["popular", "Popular"],
        ["newest", "Newest"],
        ["res_desc", "Resolution: high to low"],
        ["res_asc", "Resolution: low to high"],
        ["size", "File size"],
    ]
    readonly property var hueNames: ({
        0: "Red", 30: "Orange", 55: "Yellow", 130: "Green",
        180: "Teal", 215: "Blue", 265: "Purple", 310: "Pink",
    })
    readonly property var activeFilters: {
        const f = browse.filters
        const out = []
        for (const t of f.tags || [])
            out.push({ label: "#" + t, changes: { tags: f.tags.filter(x => x !== t) } })
        if (typeof f.hue === "number")
            out.push({ label: page.hueNames[f.hue] || "Colour", changes: { hue: -1 } })
        if (/^\d+x\d+$/.test(f.min_res))
            out.push({
                label: f.min_res === browse.screenRes ? "My screen" : f.min_res.replace("x", " × "),
                changes: { min_res: "any" },
                tip: "Exactly " + f.min_res.replace("x", " × "),
            })
        const res = { "1440p": "1440p+", "4k": "4K+", "8k": "8K" }[f.min_res]
        if (res)
            out.push({ label: res, changes: { min_res: "any" } })
        if (f.ratio && f.ratio !== "any")
            out.push({ label: f.ratio === "ultrawide" ? "Ultra-wide" : f.ratio, changes: { ratio: "any" } })
        return out
    }

    function sortLabel(key) {
        const hit = sorts.find(s => s[0] === key)
        return hit ? hit[1] : "Popular"
    }

    QQC2.ScrollBar {
        id: vbar

        anchors.top: page.top
        anchors.bottom: page.bottom
        anchors.right: page.right
    }

    GridView {
        id: grid

        anchors.fill: parent
        anchors.leftMargin: page.sideMargin
        anchors.rightMargin: page.sideMargin - page.gap
        topMargin: page.gap
        bottomMargin: 90

        readonly property int columns: Math.max(1, Math.floor(width / (page.minCardWidth + page.gap)))

        cellWidth: Math.floor(width / columns)
        cellHeight: Math.round((cellWidth - page.gap) * 10 / 16) + page.gap
        clip: true
        reuseItems: true
        model: browse.model

        QQC2.ScrollBar.vertical: vbar

        function maybeLoadMore() {
            if (count > 0 && (1 - visibleArea.yPosition - visibleArea.heightRatio) * contentHeight < height / 2)
                browse.loadMore()
        }

        onContentYChanged: maybeLoadMore()
        onCountChanged: Qt.callLater(maybeLoadMore)
        onHeightChanged: Qt.callLater(maybeLoadMore)

        header: ColumnLayout {
            width: grid.width - page.gap
            spacing: 0

            Hero {
                Layout.fillWidth: true
                Layout.preferredHeight: 290
                Layout.bottomMargin: page.gap
                logoUrl: page.logoUrl
                onDetailsRequested: {
                    const i = browse.featuredIndex()
                    if (i >= 0)
                        page.openDetail(i)
                }
                onFullscreenRequested: page.openCoverFlow(Math.max(0, browse.featuredIndex()))
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 14
                spacing: Kirigami.Units.smallSpacing * 2

                Kirigami.Heading {
                    text: "Trending"
                    level: 2
                    Layout.rightMargin: Kirigami.Units.largeSpacing
                }

                QQC2.BusyIndicator {
                    running: browse.busy
                    visible: running
                    Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                    Layout.preferredHeight: Kirigami.Units.iconSizes.medium
                }

                QQC2.Label {
                    visible: browse.checking !== ""
                    text: browse.checking
                    opacity: 0.6
                }

                Repeater {
                    model: page.activeFilters

                    delegate: Kirigami.Chip {
                        required property var modelData
                        text: modelData.label
                        checkable: false
                        closable: true
                        onRemoved: browse.applyFilters(modelData.changes)

                        QQC2.ToolTip.text: modelData.tip || ""
                        QQC2.ToolTip.visible: hovered && QQC2.ToolTip.text !== ""
                        QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
                    }
                }

                Item { Layout.fillWidth: true }

                QQC2.ComboBox {
                    readonly property var modeSources: browse.sources.filter(s => s.kind === browse.mode)

                    visible: modeSources.length > 0
                    model: modeSources
                    textRole: "label"
                    valueRole: "name"
                    currentIndex: modeSources.findIndex(s => s.name === browse.currentSource)
                    onActivated: index => browse.setSource(modeSources[index].name)
                    Accessible.name: "Source"
                }

                QQC2.ToolButton {
                    id: sortButton

                    icon.name: "view-sort"
                    text: page.sortLabel(browse.filters.sort)
                    display: QQC2.AbstractButton.TextBesideIcon
                    down: sortMenu.visible
                    onClicked: sortMenu.visible ? sortMenu.close() : sortMenu.popup(sortButton, 0, sortButton.height)

                    QQC2.Menu {
                        id: sortMenu

                        Repeater {
                            model: page.sorts

                            delegate: QQC2.MenuItem {
                                required property var modelData
                                text: modelData[1]
                                checkable: true
                                checked: browse.filters.sort === modelData[0]
                                enabled: modelData[0] === "popular" || modelData[0] === "newest"
                                         || modelData[0] === "size" || browse.filterInfo.resolution === true
                                onTriggered: browse.setSort(modelData[0])
                            }
                        }
                    }
                }

                QQC2.ToolButton {
                    id: filterButton

                    icon.name: "view-filter"
                    text: "Filter"
                    display: QQC2.AbstractButton.TextBesideIcon
                    // The desktop style draws the label across the whole background, so the badge sits in the inset.
                    rightInset: badge.visible ? badge.width + Kirigami.Units.smallSpacing : 0
                    down: filterPopup.visible
                    onClicked: filterPopup.visible ? filterPopup.close() : filterPopup.open()

                    Rectangle {
                        id: badge

                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        visible: page.activeFilters.length > 0
                        width: Math.max(height, badgeLabel.implicitWidth + 10)
                        height: badgeLabel.implicitHeight + 2
                        radius: height / 2
                        color: Kirigami.Theme.highlightColor

                        QQC2.Label {
                            id: badgeLabel
                            anchors.centerIn: parent
                            text: page.activeFilters.length
                            color: Kirigami.Theme.highlightedTextColor
                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                            font.weight: Font.DemiBold
                        }
                    }

                    App.FilterPopup {
                        id: filterPopup
                        x: filterButton.width - width
                        y: filterButton.height + Kirigami.Units.smallSpacing
                    }
                }
            }

            Kirigami.InlineMessage {
                Layout.fillWidth: true
                Layout.bottomMargin: 14
                type: Kirigami.MessageType.Error
                text: browse.errorText
                visible: browse.errorText !== ""
                actions: Kirigami.Action {
                    text: "Retry"
                    icon.name: "view-refresh"
                    onTriggered: browse.retry()
                }
            }

            Kirigami.PlaceholderMessage {
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.gridUnit * 3
                visible: grid.count === 0 && !browse.busy && browse.errorText === ""
                icon.name: "image-missing"
                text: "Nothing here yet"
                explanation: page.activeFilters.length > 0 ? "Try another source or clear your filters." : "Try another source or clear your search."
            }
        }

        delegate: Card {
            width: grid.cellWidth - page.gap
            height: grid.cellHeight - page.gap
            onClicked: page.openDetail(index)
        }
    }
}
