import QtQuick
import org.kde.kirigami as Kirigami

Kirigami.PromptDialog {
    id: prompt

    function startInstall() {
        if (svwr.distro === "opensuse")
            open()
        else
            svwr.install()
    }

    title: "Add the plugin's openSUSE repository?"
    subtitle: "Smart Video Wallpaper Reborn comes from its author's openSUSE Build Service repository (home:luisbocanegra). Xero Wallpapers will import that repository's signing key, add the repository and install the package. You'll be asked for your password."
    standardButtons: Kirigami.Dialog.Cancel
    customFooterActions: Kirigami.Action {
        text: "Add and install"
        icon.name: "list-add"
        onTriggered: {
            prompt.close()
            svwr.install(true)
        }
    }
}
