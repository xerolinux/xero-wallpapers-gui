import QtQuick
import org.kde.kirigami as Kirigami
import "." as App

Kirigami.ApplicationWindow {
    id: root

    required property url logoUrl
    property bool libraryOpen: false
    property bool editorOpen: false

    title: "Xero Wallpapers"
    width: 1280
    height: 860
    minimumWidth: 760
    minimumHeight: 560

    pageStack.globalToolBar.style: Kirigami.ApplicationHeaderStyle.None
    pageStack.initialPage: Kirigami.Page {
        padding: 0

        App.Grid {
            anchors.fill: parent
            visible: !root.libraryOpen
            logoUrl: root.logoUrl
            onOpenDetail: index => detailSheet.show(index)
            onOpenCoverFlow: index => coverFlow.openAt(index)
        }

        App.Library {
            anchors.fill: parent
            visible: root.libraryOpen
            onEditRequested: path => root.openEditor(path)
        }
    }

    function openEditor(path) {
        editor.open(path)
        root.editorOpen = true
    }

    App.DetailSheet {
        id: detailSheet
        onCropRequested: index => downloads.edit(index)
    }

    App.CoverFlow {
        id: coverFlow
        logoUrl: root.logoUrl
        onCropRequested: index => {
            root.showPassiveNotification("Getting the image ready for the editor")
            downloads.edit(index)
        }
    }

    App.Editor {
        anchors.fill: parent
        z: 20
        visible: root.editorOpen
        onCloseRequested: root.editorOpen = false
    }

    Connections {
        target: downloads

        function onEditReady(title, path) {
            detailSheet.close()
            root.openEditor(path)
        }
    }

    Connections {
        target: editor

        function onSaved(path, wasSet) {
            root.showPassiveNotification("Saved " + path.split("/").pop() + (wasSet ? " · set as wallpaper" : ""))
        }

        function onFailed(message) {
            root.showPassiveNotification(message, "long")
        }
    }

    Connections {
        target: downloads
        enabled: !detailSheet.visible && !coverFlow.visible

        function onFinished(title, path, wasSet, existing) {
            if (existing)
                root.showPassiveNotification("Already in your Library" + (wasSet ? " · set as wallpaper" : ""))
            else
                root.showPassiveNotification(wasSet ? "Wallpaper set: " + title : "Saved " + path)
        }

        function onFailed(title, message) {
            root.showPassiveNotification("Couldn't get " + title + ": " + message, "long")
        }
    }

    Connections {
        target: library

        function onWallpaperSet(name) {
            root.showPassiveNotification("Wallpaper set: " + name)
        }

        function onFailed(message) {
            root.showPassiveNotification(message, "long")
        }
    }

    App.SettingsDialog {
        id: settingsDialog
    }

    App.AboutDialog {
        id: aboutDialog
        backdrop: root.contentItem
        logoUrl: root.logoUrl
    }

    App.SetupWizard {
        id: setupWizard
        backdrop: root.contentItem
        logoUrl: root.logoUrl
    }

    Kirigami.PromptDialog {
        id: slideshowPrompt

        property bool confirmed: false

        title: "Replace the live wallpaper?"
        subtitle: "A live wallpaper is playing. Changing wallpapers automatically switches your desktop to a slideshow of your Wallpapers folder."
        standardButtons: Kirigami.Dialog.Cancel
        customFooterActions: Kirigami.Action {
            text: "Switch to slideshow"
            icon.name: "preferences-desktop-wallpaper"
            onTriggered: {
                slideshowPrompt.confirmed = true
                slideshowPrompt.close()
                settings.confirmSlideshow()
            }
        }
        onOpened: confirmed = false
        onClosed: {
            if (!confirmed)
                settings.cancelSlideshow()
        }
    }

    Connections {
        target: settings

        function onSetupRequested() {
            settingsDialog.close()
            setupWizard.start()
        }

        function onConfirmSlideshowOverLive() {
            slideshowPrompt.open()
        }

        function onSlideshowFailed(message) {
            root.showPassiveNotification("Couldn't change the wallpaper automatically: " + message, "long")
        }
    }

    Component.onCompleted: {
        if (!settings.firstRunDone)
            setupWizard.start()
    }

    Column {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 14
        anchors.rightMargin: 26
        spacing: Kirigami.Units.smallSpacing
        z: 10

        App.AppUpdatePill {
            anchors.right: parent.right
        }

        App.UpdatePill {
            anchors.right: parent.right
            onDetailsRequested: settingsDialog.openAt("live")
        }
    }

    Connections {
        target: appUpdate

        function onFailed(message) {
            root.showPassiveNotification("Couldn't update Xero Wallpapers: " + message, "long")
        }
    }

    App.Dock {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 18
        z: 10
        libraryOpen: root.libraryOpen
        onSettingsRequested: settingsDialog.open()
        onAboutRequested: aboutDialog.open()
        onLibraryRequested: root.libraryOpen = true
        onBrowseRequested: mode => {
            root.libraryOpen = false
            browse.setMode(mode)
        }
    }
}
