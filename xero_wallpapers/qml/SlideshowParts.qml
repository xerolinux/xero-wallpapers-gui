import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "Slideshow.js" as Slide

QtObject {
    component IntervalPicker: RowLayout {
        id: picker

        property int minutes: 60
        readonly property int customIndex: Slide.PRESETS.length
        property int index: indexFor(minutes)
        readonly property bool custom: index === customIndex

        signal picked(int minutes)

        function indexFor(m) {
            var i = Slide.PRESETS.indexOf(m)
            return i < 0 ? customIndex : i
        }

        spacing: Kirigami.Units.smallSpacing
        onMinutesChanged: index = indexFor(minutes)

        QQC2.Slider {
            id: slider

            Layout.preferredWidth: Kirigami.Units.gridUnit * 9
            from: 0
            to: picker.customIndex
            stepSize: 1
            snapMode: QQC2.Slider.SnapAlways
            value: picker.index
            onMoved: {
                picker.index = value
                if (!picker.custom)
                    debounce.restart()
            }
        }

        QQC2.Label {
            Layout.preferredWidth: Kirigami.Units.gridUnit * 3.5
            text: picker.custom ? "Custom" : Slide.intervalLabel(Slide.PRESETS[slider.value])
        }

        QQC2.SpinBox {
            id: spin

            visible: picker.custom
            from: 1
            to: 10080
            editable: true
            value: picker.minutes
            textFromValue: (value, locale) => value + " min"
            valueFromText: (text, locale) => parseInt(text) || 1
            onValueModified: debounce.restart()
        }

        Timer {
            id: debounce

            interval: 500
            onTriggered: picker.picked(picker.custom ? spin.value : Slide.PRESETS[slider.value])
        }
    }

    component DurationPicker: RowLayout {
        id: duration

        property int ms: 1200

        signal picked(int ms)

        spacing: Kirigami.Units.smallSpacing

        QQC2.Slider {
            id: durationSlider

            Layout.preferredWidth: Kirigami.Units.gridUnit * 9
            from: 500
            to: 3000
            stepSize: 100
            snapMode: QQC2.Slider.SnapAlways
            value: duration.ms
            onMoved: durationDebounce.restart()
        }

        QQC2.Label {
            Layout.preferredWidth: Kirigami.Units.gridUnit * 3.5
            text: Slide.durationLabel(durationSlider.value)
        }

        Timer {
            id: durationDebounce

            interval: 500
            onTriggered: duration.picked(Math.round(durationSlider.value))
        }
    }

    component ChoiceBox: QQC2.ComboBox {
        id: box

        property string value
        property var choices: []

        signal picked(string value)

        textRole: "text"
        valueRole: "value"
        model: choices
        onActivated: box.picked(currentValue)
        onValueChanged: currentIndex = indexOfValue(value)
        Component.onCompleted: currentIndex = indexOfValue(value)
    }
}
