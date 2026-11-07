import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ShadowedRectangle {
    id: dock

    property bool searching: false
    property bool libraryOpen: false

    signal settingsRequested()
    signal browseRequested(string mode)
    signal libraryRequested()
    signal aboutRequested()

    function closeSearch() {
        searching = false
        if (field.text !== "") {
            field.text = ""
            browse.search("")
        }
    }

    implicitWidth: row.implicitWidth + 12
    implicitHeight: row.implicitHeight + 12
    radius: 20
    color: Qt.alpha(Kirigami.Theme.backgroundColor, 0.9)
    border.width: 1
    border.color: Qt.alpha(Kirigami.Theme.textColor, 0.15)
    shadow.size: 30
    shadow.yOffset: 10
    shadow.color: Qt.rgba(0, 0, 0, 0.35)

    // Floats over the grid: swallow presses and hover in the gaps so they never reach the cards beneath.
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        hoverEnabled: true
    }

    component NavButton: QQC2.ToolButton {
        implicitHeight: 44
        display: QQC2.AbstractButton.TextBesideIcon
    }

    RowLayout {
        id: row

        anchors.centerIn: parent
        spacing: 4

        NavButton {
            text: "Wallpapers"
            icon.name: "preferences-desktop-wallpaper"
            checked: !dock.libraryOpen && browse.mode === "static"
            onClicked: dock.browseRequested("static")
        }

        NavButton {
            text: "Live"
            icon.name: "video-x-generic"
            visible: browse.liveEnabled
            checked: !dock.libraryOpen && browse.mode === "live"
            onClicked: dock.browseRequested("live")
        }

        NavButton {
            text: "Library"
            icon.name: "folder-pictures"
            checked: dock.libraryOpen
            onClicked: dock.libraryRequested()
        }

        Kirigami.Separator {
            Layout.preferredHeight: 26
            Layout.leftMargin: 4
            Layout.rightMargin: 4
        }

        Kirigami.SearchField {
            id: field

            Layout.preferredWidth: dock.searching ? 260 : 0
            visible: Layout.preferredWidth > 0
            autoAccept: false
            onAccepted: {
                dock.browseRequested(browse.mode)
                browse.search(text)
            }
            Keys.onEscapePressed: dock.closeSearch()

            Behavior on Layout.preferredWidth {
                NumberAnimation { duration: Kirigami.Units.longDuration; easing.type: Easing.OutCubic }
            }
        }

        NavButton {
            text: dock.searching ? "" : "Search"
            icon.name: dock.searching ? "dialog-close" : "search"
            onClicked: {
                if (dock.searching) {
                    dock.closeSearch()
                } else {
                    dock.searching = true
                    field.forceActiveFocus()
                }
            }
        }

        NavButton {
            text: "Settings"
            icon.name: "configure"
            onClicked: dock.settingsRequested()
        }

        NavButton {
            text: "About"
            icon.name: "help-about"
            onClicked: dock.aboutRequested()
        }
    }
}
