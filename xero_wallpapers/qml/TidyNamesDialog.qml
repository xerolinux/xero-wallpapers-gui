import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.Dialog {
    id: dialog

    property string kind: "static"
    property var rows: []
    property var checks: []
    property bool waiting: false
    readonly property int checkedCount: checks.filter(c => c).length
    readonly property bool empty: !waiting && rows.length === 0
    readonly property bool canRename: !waiting && !library.tidying && checkedCount > 0

    function propose(k) {
        kind = k
        rows = []
        checks = []
        waiting = true
        open()
        library.proposeTidy(k)
    }

    function toggle(i, on) {
        const next = checks.slice()
        next[i] = on
        checks = next
    }

    function rename() {
        if (!canRename)
            return
        library.applyTidy(kind, rows.filter((r, i) => checks[i]))
        close()
    }

    title: "Tidy names"
    preferredWidth: Kirigami.Units.gridUnit * 36
    standardButtons: Kirigami.Dialog.NoButton
    onClosed: waiting = false

    customFooterActions: [
        Kirigami.Action {
            text: dialog.checkedCount > 0 ? "Rename " + dialog.checkedCount : "Rename"
            icon.name: "edit-rename"
            enabled: dialog.canRename
            onTriggered: dialog.rename()
        },
        Kirigami.Action {
            text: "Cancel"
            icon.name: "dialog-cancel"
            onTriggered: dialog.close()
        }
    ]

    Connections {
        target: library

        function onTidyProposed(list) {
            if (!dialog.waiting)
                return
            dialog.rows = list
            dialog.checks = list.map(() => true)
            dialog.waiting = false
        }
    }

    ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.largeSpacing
            visible: dialog.waiting
            spacing: Kirigami.Units.largeSpacing

            QQC2.BusyIndicator {
                running: dialog.waiting
            }

            QQC2.Label {
                Layout.fillWidth: true
                text: "Looking for names to tidy. Wallhaven files need their tags, which can take a while."
                wrapMode: Text.WordWrap
            }
        }

        Kirigami.PlaceholderMessage {
            Layout.fillWidth: true
            Layout.margins: Kirigami.Units.gridUnit
            visible: dialog.empty
            icon.name: "checkmark"
            text: "Nothing to tidy"
            explanation: "Every file name here is already readable."
        }

        QQC2.Label {
            Layout.fillWidth: true
            Layout.leftMargin: Kirigami.Units.largeSpacing
            Layout.rightMargin: Kirigami.Units.largeSpacing
            visible: dialog.rows.length > 0
            text: "These files will be renamed. Nothing is overwritten, and your current wallpaper keeps working."
            wrapMode: Text.WordWrap
            opacity: 0.7
        }

        ListView {
            id: list

            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(contentHeight, Kirigami.Units.gridUnit * 18)
            visible: dialog.rows.length > 0
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
                    Accessible.name: "Rename " + row.modelData.old + " to " + row.modelData.new
                }

                QQC2.Label {
                    Layout.preferredWidth: row.nameWidth
                    text: row.modelData.old
                    elide: Text.ElideMiddle
                    opacity: 0.7
                }

                Kirigami.Icon {
                    id: arrow
                    source: "go-next"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                }

                QQC2.Label {
                    Layout.preferredWidth: row.nameWidth
                    Layout.rightMargin: Kirigami.Units.largeSpacing
                    text: row.modelData.new
                    font.weight: Font.DemiBold
                    elide: Text.ElideMiddle
                }
            }
        }
    }
}
