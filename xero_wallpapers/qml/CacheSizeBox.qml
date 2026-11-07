import QtQuick
import QtQuick.Controls as QQC2

QQC2.ComboBox {
    id: box

    property int value: 500

    signal picked(int size)

    textRole: "text"
    valueRole: "size"
    model: [
        { text: "250 MB", size: 250 },
        { text: "500 MB", size: 500 },
        { text: "1 GB", size: 1000 }
    ]
    onActivated: box.picked(currentValue)
    onValueChanged: currentIndex = indexOfValue(value)
    Component.onCompleted: currentIndex = indexOfValue(value)
}
