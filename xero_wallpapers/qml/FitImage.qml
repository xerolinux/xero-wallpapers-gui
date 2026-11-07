import QtQuick
import QtQuick.Effects
import org.kde.kirigami as Kirigami

// Shows the whole image (never cropped), centred over a blurred, dimmed fill of the same picture.
Item {
    id: fit

    property alias source: picture.source
    property alias sourceSize: picture.sourceSize
    property alias asynchronous: picture.asynchronous
    readonly property alias status: picture.status
    property url fillSource
    property real radius
    property real fillDim: 0.35
    // Sources without a pre-blurred "image://thumb/blur" variant (e.g. grabbed video frames) blur here instead.
    property bool blurFill: false

    readonly property real aspect: picture.implicitHeight > 0 ? picture.implicitWidth / picture.implicitHeight : 0

    Kirigami.ShadowedImage {
        id: fill

        anchors.fill: parent
        radius: fit.radius
        color: "transparent"
        source: fit.fillSource
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        visible: fit.fillSource.toString() !== "" && picture.status === Image.Ready
        layer.enabled: fit.blurFill
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: 1
            blurMax: 32
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: fit.radius
        color: "black"
        opacity: fit.fillDim
        visible: fill.visible
    }

    Image {
        id: picture

        readonly property bool wide: fit.aspect >= fit.width / Math.max(1, fit.height)

        anchors.centerIn: parent
        width: fit.aspect > 0 ? (wide ? fit.width : Math.round(fit.height * fit.aspect)) : fit.width
        height: fit.aspect > 0 ? (wide ? Math.round(fit.width / fit.aspect) : fit.height) : fit.height
        fillMode: Image.Stretch
        asynchronous: true
    }

    ShaderEffectSource {
        id: texture

        sourceItem: picture
        hideSource: true
    }

    Kirigami.ShadowedTexture {
        anchors.fill: picture
        radius: fit.radius
        color: "transparent"
        source: picture.status === Image.Ready ? texture : null
    }
}
