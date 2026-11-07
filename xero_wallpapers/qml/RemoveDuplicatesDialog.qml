import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.Dialog {
    id: dialog

    property var rows: []
    property var checks: []
    readonly property int checkedCount: checks.filter(c => c).length

    function show(list) {
        rows = list
        checks = list.map(() => true)
        open()
    }

    function toggle(i, on) {
        const next = checks.slice()
        next[i] = on
        checks = next
    }

    function remove() {
        library.removeDuplicates(rows.filter((r, i) => checks[i]).map(r => r.path))
        close()
    }

    title: "Remove duplicates"
    preferredWidth: Kirigami.Units.gridUnit * 36
    standardButtons: Kirigami.Dialog.NoButton

    customFooterActions: [
        Kirigami.Action {
            text: dialog.checkedCount > 0 ? "Move " + dialog.checkedCount + " to Trash" : "Move to Trash"
            icon.name: "edit-delete"
            enabled: dialog.checkedCount > 0
            onTriggered: dialog.remove()
        },
        Kirigami.Action {
            text: "Cancel"
            icon.name: "dialog-cancel"
            onTriggered: dialog.close()
        }
    ]

    ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        QQC2.Label {
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.largeSpacing
            Layout.rightMargin: Kirigami.Units.largeSpacing
            text: "These files are extra copies of a picture you already have. The largest copy is kept."
            wrapMode: Text.WordWrap
            opacity: 0.7
        }

        ListView {
            id: list

            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(contentHeight, Kirigami.Units.gridUnit * 18)
            clip: true
            model: dialog.rows
            QQC2.ScrollBar.vertical: QQC2.ScrollBar {}

            delegate: RowLayout {
                id: row

                required property var modelData
                required property int index
                readonly property int nameWidth: Math.max(0, (width - box.width - arrow.width
                                                             - Kirigami.Units.largeSpacing - spacing * 3) / 2)

                width: list.width
                spacing: Kirigami.Units.smallSpacing

                TapHandler {
                    gesturePolicy: TapHandler.WithinBounds
                    grabPermissions: PointerHandler.TakeOverForbidden
                    onTapped: dialog.toggle(row.index, !box.checked)
                }

                QQC2.CheckBox {
                    id: box
                    checked: dialog.checks[row.index] === true
                    onToggled: dialog.toggle(row.index, checked)
                    Accessible.name: "Remove " + row.modelData.name
                }

                QQC2.Label {
                    Layout.preferredWidth: row.nameWidth
                    text: row.modelData.name
                    font.weight: Font.DemiBold
                    elide: Text.ElideMiddle
                }

                Kirigami.Icon {
                    id: arrow
                    source: "edit-copy"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    opacity: 0.7
                }

                QQC2.Label {
                    Layout.preferredWidth: row.nameWidth
                    Layout.rightMargin: Kirigami.Units.largeSpacing
                    text: "copy of " + row.modelData.keep
                    elide: Text.ElideMiddle
                    opacity: 0.7
                }
            }
        }
    }
}
