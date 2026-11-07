import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "." as App

QQC2.ScrollView {
    id: page

    property bool adding: false
    property string kind: "static"
    property string parser: "json"
    property string message: ""
    property int messageType: Kirigami.MessageType.Information

    function config() {
        const fields = {
            title: titleField.text.trim(),
            thumb: thumbField.text.trim(),
            link: linkField.text.trim()
        }
        const optional = { resolution: resField, width: widthField, height: heightField,
                           tags: tagsField, author: authorField, size: sizeField }
        for (const key in optional) {
            const value = optional[key].text.trim()
            if (value)
                fields[key] = value
        }
        const cfg = {
            name: nameField.text.trim(),
            kind: page.kind,
            parser: page.parser,
            search_url: urlField.text.trim(),
            items: itemsField.text.trim(),
            fields: fields
        }
        const detail = detailField.text.trim()
        if (detail)
            cfg.detail_download = detail
        return cfg
    }

    function hint(json, html) {
        return parser === "json" ? json : html
    }

    function showErrors(errors) {
        messageType = Kirigami.MessageType.Error
        message = errors.join("\n")
    }

    function resetForm() {
        for (const f of [nameField, urlField, itemsField, titleField, thumbField, linkField,
                         resField, widthField, heightField, tagsField, authorField, sizeField, detailField])
            f.text = ""
        message = ""
        adding = false
    }

    contentWidth: availableWidth
    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

    Connections {
        target: settings

        function onTestResult(result) {
            page.messageType = result.ok ? Kirigami.MessageType.Positive : Kirigami.MessageType.Error
            page.message = result.ok
                ? ["Found " + result.count + " items. First item:"].concat(result.fields).join("\n")
                : "Test failed: " + result.message
        }
    }

    component MonoField: QQC2.TextField {
        Layout.fillWidth: true
        font.family: "monospace"
    }

    component Segmented: RowLayout {
        id: seg

        property var options: []
        property string value

        signal picked(string value)

        spacing: 0

        QQC2.ButtonGroup { id: group }

        Repeater {
            model: seg.options

            delegate: QQC2.Button {
                required property var modelData

                text: modelData.label
                checkable: true
                checked: seg.value === modelData.value
                QQC2.ButtonGroup.group: group
                onClicked: seg.picked(modelData.value)
            }
        }
    }

    ColumnLayout {
        width: page.availableWidth
        spacing: Kirigami.Units.largeSpacing

        App.SettingsParts.PageHeader {
            Layout.margins: Kirigami.Units.gridUnit
            Layout.bottomMargin: 0
            title: "Sources"
            lead: "Pick where wallpapers come from. Add your own source with a search URL and a parser."
        }

        App.SettingsParts.Group {
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.rightMargin: Kirigami.Units.gridUnit
            visible: page.adding
            border.color: Kirigami.Theme.highlightColor

            GridLayout {
                Layout.fillWidth: true
                Layout.margins: Kirigami.Units.largeSpacing
                columns: 2
                columnSpacing: Kirigami.Units.largeSpacing
                rowSpacing: Kirigami.Units.smallSpacing

                QQC2.Label { text: "Name" }
                QQC2.TextField {
                    id: nameField
                    Layout.fillWidth: true
                    placeholderText: "e.g. My Gallery"
                }

                QQC2.Label { text: "Type" }
                Segmented {
                    options: [{ label: "Static", value: "static" }, { label: "Live", value: "live" }]
                    value: page.kind
                    onPicked: v => page.kind = v
                }

                QQC2.Label { text: "Search URL" }
                QQC2.TextField {
                    id: urlField
                    Layout.fillWidth: true
                    font.family: "monospace"
                    placeholderText: "https://example.com/api?q={query}&page={page}"
                }

                QQC2.Label { text: "Parser" }
                Segmented {
                    options: [{ label: "JSON API", value: "json" }, { label: "HTML page", value: "html" }]
                    value: page.parser
                    onPicked: v => page.parser = v
                }

                QQC2.Label { text: page.parser === "json" ? "Items path" : "Item selector" }
                QQC2.TextField {
                    id: itemsField
                    Layout.fillWidth: true
                    font.family: "monospace"
                    placeholderText: page.parser === "json" ? "data[]" : "div.wallpaper"
                }

                QQC2.Label { text: "Title" }
                QQC2.TextField {
                    id: titleField
                    Layout.fillWidth: true
                    font.family: "monospace"
                    placeholderText: page.parser === "json" ? "data[].title" : "a@title"
                }

                QQC2.Label { text: "Thumbnail" }
                QQC2.TextField {
                    id: thumbField
                    Layout.fillWidth: true
                    font.family: "monospace"
                    placeholderText: page.parser === "json" ? "data[].thumbs.large" : "img@src"
                }

                QQC2.Label { text: "Download or detail link" }
                QQC2.TextField {
                    id: linkField
                    Layout.fillWidth: true
                    font.family: "monospace"
                    placeholderText: page.parser === "json" ? "data[].url" : "a@href"
                }

                QQC2.Label {
                    Layout.columnSpan: 2
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    text: "Optional"
                    font.weight: Font.DemiBold
                    opacity: 0.7
                }

                QQC2.Label { text: "Resolution" }
                MonoField { id: resField; placeholderText: page.hint("data[].resolution", ".resolution") }

                QQC2.Label { text: "Width" }
                MonoField { id: widthField; placeholderText: page.hint("data[].dimension_x", "img@data-width") }

                QQC2.Label { text: "Height" }
                MonoField { id: heightField; placeholderText: page.hint("data[].dimension_y", "img@data-height") }

                QQC2.Label { text: "Tags" }
                MonoField { id: tagsField; placeholderText: page.hint("data[].tags", ".tags") }

                QQC2.Label { text: "Author" }
                MonoField { id: authorField; placeholderText: page.hint("data[].uploader", ".author") }

                QQC2.Label { text: "File size" }
                MonoField { id: sizeField; placeholderText: page.hint("data[].file_size", ".size") }

                QQC2.Label { text: "Detail page download selector" }
                MonoField { id: detailField; placeholderText: "a.download" }

                Kirigami.InlineMessage {
                    Layout.columnSpan: 2
                    Layout.fillWidth: true
                    visible: page.message !== ""
                    type: page.messageType
                    text: page.message
                }

                RowLayout {
                    Layout.columnSpan: 2
                    Layout.alignment: Qt.AlignRight

                    QQC2.Button {
                        text: "Cancel"
                        flat: true
                        onClicked: page.resetForm()
                    }

                    QQC2.Button {
                        text: "Test"
                        icon.name: "media-playback-start"
                        onClicked: {
                            const result = settings.testCustomSource(page.config())
                            if (result.errors) {
                                page.showErrors(result.errors)
                            } else {
                                page.messageType = Kirigami.MessageType.Information
                                page.message = "Testing…"
                            }
                        }
                    }

                    QQC2.Button {
                        text: "Save source"
                        icon.name: "dialog-ok-apply"
                        highlighted: true
                        onClicked: {
                            const errors = settings.addCustomSource(page.config())
                            if (errors.length)
                                page.showErrors(errors)
                            else
                                page.resetForm()
                        }
                    }
                }
            }
        }

        App.SettingsParts.Group {
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.rightMargin: Kirigami.Units.gridUnit

            Repeater {
                model: settings.sources

                delegate: App.SettingsParts.Row {
                    required property var modelData
                    required property int index

                    separator: index > 0
                    title: modelData.label
                    subtitle: modelData.url
                    monoSubtitle: true
                    enabled: modelData.kind === "static" || settings.liveEnabled
                    leading: Rectangle {
                        implicitWidth: Kirigami.Units.iconSizes.medium
                        implicitHeight: implicitWidth
                        radius: Kirigami.Units.cornerRadius * 2
                        color: modelData.kind === "live" ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.highlightColor

                        QQC2.Label {
                            anchors.centerIn: parent
                            text: modelData.label.charAt(0).toUpperCase()
                            color: Kirigami.Theme.highlightedTextColor
                            font.weight: Font.Bold
                        }
                    }

                    Kirigami.Chip {
                        text: modelData.kind === "live" ? "Live" : "Static"
                        closable: false
                        checkable: false
                    }

                    QQC2.ToolButton {
                        visible: !modelData.builtin
                        icon.name: "edit-delete"
                        display: QQC2.AbstractButton.IconOnly
                        text: "Remove " + modelData.label
                        QQC2.ToolTip.text: text
                        QQC2.ToolTip.visible: hovered
                        onClicked: settings.removeCustomSource(modelData.name)
                    }

                    QQC2.Switch {
                        checked: modelData.enabled
                        onToggled: settings.setSourceEnabled(modelData.name, checked)
                    }
                }
            }
        }

        QQC2.Button {
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.bottomMargin: Kirigami.Units.gridUnit
            visible: !page.adding
            text: "Add source"
            icon.name: "list-add"
            onClicked: page.adding = true
        }
    }
}
