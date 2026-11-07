import QtQuick
import org.kde.plasma.plasmoid

WallpaperItem {
    id: root

    readonly property var cfg: root.configuration

    Component.onCompleted: root.loading = true

    Rectangle {
        anchors.fill: parent
        color: "black"
    }

    SlideshowView {
        anchors.fill: parent
        folder: root.cfg.SlideFolder
        interval: Math.max(60, root.cfg.SlideInterval)
        order: root.cfg.SlideOrder
        transition: root.cfg.Transition
        duration: root.cfg.TransitionDuration
        fillMode: root.cfg.FillMode
        onShown: root.loading = false
        onSwitched: root.accentColorChanged()
    }
}
