import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Effects
import org.kde.kirigami as Kirigami

QQC2.Popup {
    id: card

    property Item backdrop
    property int preferredWidth: 860
    property int preferredHeight: 580
    readonly property real radius: Kirigami.Units.cornerRadius * 3
    default property alias content: inner.data

    parent: QQC2.Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(preferredWidth, parent ? parent.width - Kirigami.Units.gridUnit * 2 : preferredWidth)
    height: Math.min(preferredHeight, parent ? parent.height - Kirigami.Units.gridUnit * 2 : preferredHeight)
    padding: 0
    modal: true
    focus: true

    QQC2.Overlay.modal: Item {
        ShaderEffectSource {
            id: snapshot
            anchors.fill: parent
            sourceItem: card.backdrop
            visible: false
        }

        MultiEffect {
            anchors.fill: parent
            source: snapshot
            visible: card.backdrop !== null
            autoPaddingEnabled: false
            blurEnabled: true
            blur: 1
            blurMax: 48
        }

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0, 0, 0, 0.45)
        }
    }

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Kirigami.Units.longDuration; easing.type: Easing.OutCubic }
        NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Kirigami.Units.longDuration; easing.type: Easing.OutCubic }
    }

    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Kirigami.Units.shortDuration }
    }

    background: Kirigami.ShadowedRectangle {
        radius: card.radius
        color: Kirigami.Theme.backgroundColor
        border.width: 1
        border.color: Qt.alpha(Kirigami.Theme.textColor, 0.12)
        shadow.size: 40
        shadow.yOffset: 12
        shadow.color: Qt.rgba(0, 0, 0, 0.4)
    }

    contentItem: Item {
        // A TapHandler in the content only grabs passively, so without this the press also reaches the grid below.
        TapHandler {
            acceptedButtons: Qt.AllButtons
            gesturePolicy: TapHandler.WithinBounds
            grabPermissions: PointerHandler.TakeOverForbidden
        }

        Item {
            id: inner

            anchors.fill: parent
            layer.enabled: true
            layer.effect: MultiEffect {
                maskEnabled: true
                maskSource: mask
                maskThresholdMin: 0.5
                maskSpreadAtMin: 1
            }
        }

        Rectangle {
            id: mask

            anchors.fill: parent
            radius: card.radius
            visible: false
            layer.enabled: true
        }
    }
}
