import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Dialogs
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: root

    property string cfg_SlideFolder
    property int cfg_SlideInterval
    property int cfg_SlideOrder
    property string cfg_Transition
    property int cfg_TransitionDuration
    property int cfg_FillMode

    function tr(text) {
        // qmllint disable unqualified
        return i18nd("plasma_wallpaper_org.xerolinux.wallpapers.slideshow", text);
    }

    Kirigami.InlineMessage {
        Layout.fillWidth: true
        visible: true
        type: Kirigami.MessageType.Information
        text: root.tr("Configure in Xero Wallpapers. The main options can also be changed here.")
    }

    Kirigami.FormLayout {
        Layout.fillWidth: true

        RowLayout {
            Kirigami.FormData.label: root.tr("Folder:")
            QQC2.TextField {
                Layout.fillWidth: true
                text: root.cfg_SlideFolder
                onTextEdited: root.cfg_SlideFolder = text
            }
            QQC2.Button {
                icon.name: "folder-open"
                text: root.tr("Browse")
                onClicked: folderDialog.open()
            }
        }

        QQC2.SpinBox {
            Kirigami.FormData.label: root.tr("Change every (minutes):")
            from: 1
            to: 10080
            value: Math.round(root.cfg_SlideInterval / 60)
            onValueModified: root.cfg_SlideInterval = value * 60
        }

        QQC2.ComboBox {
            Kirigami.FormData.label: root.tr("Order:")
            model: [root.tr("Random"), root.tr("By name")]
            currentIndex: root.cfg_SlideOrder
            onActivated: index => root.cfg_SlideOrder = index
        }

        QQC2.ComboBox {
            Kirigami.FormData.label: root.tr("Transition:")
            textRole: "text"
            valueRole: "value"
            model: [
                { text: root.tr("Fade"), value: "fade" },
                { text: root.tr("Slide"), value: "slide" },
                { text: root.tr("Wipe"), value: "wipe" },
                { text: root.tr("Grow"), value: "grow" },
                { text: root.tr("Zoom"), value: "zoom" },
                { text: root.tr("Pixelate"), value: "pixelate" },
                { text: root.tr("Wave"), value: "wave" },
                { text: root.tr("Random"), value: "random" }
            ]
            currentIndex: Math.max(0, indexOfValue(root.cfg_Transition))
            onActivated: root.cfg_Transition = currentValue
        }

        RowLayout {
            Kirigami.FormData.label: root.tr("Transition duration:")
            QQC2.Slider {
                id: durationSlider
                from: 500
                to: 3000
                stepSize: 100
                value: root.cfg_TransitionDuration
                onMoved: root.cfg_TransitionDuration = value
            }
            QQC2.Label {
                text: root.tr("%1 s").arg((durationSlider.value / 1000).toFixed(1))
            }
        }

        QQC2.ComboBox {
            Kirigami.FormData.label: root.tr("Positioning:")
            textRole: "text"
            valueRole: "value"
            model: [
                { text: root.tr("Scaled and cropped"), value: Image.PreserveAspectCrop },
                { text: root.tr("Scaled"), value: Image.Stretch },
                { text: root.tr("Scaled, keep proportions"), value: Image.PreserveAspectFit },
                { text: root.tr("Centered"), value: Image.Pad },
                { text: root.tr("Tiled"), value: Image.Tile }
            ]
            currentIndex: Math.max(0, indexOfValue(root.cfg_FillMode))
            onActivated: root.cfg_FillMode = currentValue
        }
    }

    FolderDialog {
        id: folderDialog
        currentFolder: root.cfg_SlideFolder ? "file://" + root.cfg_SlideFolder.split("/").map(encodeURIComponent).join("/") : ""
        onAccepted: root.cfg_SlideFolder = decodeURIComponent(selectedFolder.toString().replace(/^file:\/\//, ""))
    }
}
