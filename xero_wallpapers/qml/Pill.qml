import QtQuick
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ShadowedRectangle {
    id: pill

    property bool shown: false
    default property alias content: row.data

    visible: opacity > 0
    opacity: shown ? 1 : 0
    implicitWidth: row.implicitWidth + Kirigami.Units.largeSpacing + Kirigami.Units.smallSpacing
    implicitHeight: row.implicitHeight + Kirigami.Units.smallSpacing * 2
    radius: height / 2
    color: Qt.alpha(Kirigami.Theme.backgroundColor, 0.92)
    border.width: 1
    border.color: Qt.alpha(Kirigami.Theme.textColor, 0.15)
    shadow.size: 20
    shadow.yOffset: 6
    shadow.color: Qt.rgba(0, 0, 0, 0.3)

    Behavior on opacity {
        NumberAnimation { duration: Kirigami.Units.longDuration }
    }

    // Floats over the grid: swallow presses and hover in the gaps so they never reach the cards beneath.
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        hoverEnabled: true
    }

    RowLayout {
        id: row

        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.leftMargin: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.largeSpacing
    }
}
