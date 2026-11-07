pragma ComponentBehavior: Bound

import QtQuick
import org.kde.kirigami as Kirigami

Rectangle {
    id: preview

    property string transition: "fade"
    property int duration: 1200
    property string shaderDir
    property real progress: 0
    property string kind: ""
    property Item front: first
    property Item back: second
    readonly property var kinds: ["fade", "slide", "wipe", "grow", "zoom", "pixelate", "wave"]
    readonly property var shaderKinds: ["wipe", "grow", "pixelate", "wave"]
    readonly property bool shaderActive: anim.running && shaderDir !== "" && shaderKinds.indexOf(kind) >= 0

    function play() {
        if (anim.running || !visible)
            return;
        if (transition === "random") {
            const others = kinds.filter(k => k !== kind);
            kind = others[Math.floor(Math.random() * others.length)];
        } else {
            kind = kinds.indexOf(transition) >= 0 ? transition : "fade";
        }
        if (shaderDir === "" && shaderKinds.indexOf(kind) >= 0)
            kind = "fade";
        front.z = 1;
        back.z = 2;
        back.opacity = kind === "fade" || kind === "zoom" ? 0 : 1;
        progress = 0;
        apply();
        anim.restart();
    }

    function replay() {
        if (anim.running)
            anim.complete();
        play();
        // Timer.restart() would drop the visibility binding and keep the loop running while hidden.
        loop.running = false;
        loop.running = Qt.binding(() => preview.visible);
    }

    function apply() {
        const p = progress;
        switch (kind) {
        case "fade":
            back.opacity = p;
            break;
        case "slide":
            back.x = width * (1 - p);
            front.x = -width * p;
            break;
        case "zoom":
            back.opacity = p;
            back.scale = 1.12 - 0.12 * p;
            front.scale = 1 + 0.05 * p;
            break;
        }
    }

    function finish() {
        const old = front;
        front = back;
        back = old;
        for (const item of [front, back]) {
            item.x = 0;
            item.scale = 1;
        }
        front.opacity = 1;
        front.z = 1;
        back.opacity = 0;
        back.z = 0;
    }

    implicitWidth: Kirigami.Units.gridUnit * 4
    implicitHeight: Kirigami.Units.gridUnit * 2.25
    radius: Kirigami.Units.cornerRadius
    color: Kirigami.Theme.backgroundColor
    clip: true

    onProgressChanged: apply()
    onTransitionChanged: replay()
    onDurationChanged: replay()

    Timer {
        id: loop

        interval: Math.max(3000, preview.duration + 2000)
        repeat: true
        running: preview.visible
        triggeredOnStart: true
        onTriggered: preview.play()
    }

    NumberAnimation {
        id: anim

        target: preview
        property: "progress"
        from: 0
        to: 1
        duration: Math.max(1, preview.duration)
        easing.type: Easing.OutCubic
        onFinished: preview.finish()
    }

    component Scene: Rectangle {
        id: scene

        property alias icon: glyph.source
        property color tint

        width: preview.width
        height: preview.height
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: scene.tint }
            GradientStop { position: 1; color: Qt.darker(scene.tint, 1.8) }
        }

        Kirigami.Icon {
            id: glyph

            anchors.centerIn: parent
            width: parent.height * 0.6
            height: width
            color: Kirigami.Theme.highlightedTextColor
            isMask: true
        }
    }

    Scene {
        id: first

        tint: Kirigami.Theme.highlightColor
        icon: "weather-clear"
    }

    Scene {
        id: second

        opacity: 0
        tint: Kirigami.Theme.positiveTextColor
        icon: "weather-clear-night"
    }

    Loader {
        anchors.fill: parent
        z: 3
        active: preview.shaderActive
        sourceComponent: Item {
            ShaderEffectSource {
                id: fromTexture

                sourceItem: preview.front
                hideSource: true
                visible: false
            }

            ShaderEffectSource {
                id: toTexture

                sourceItem: preview.back
                hideSource: true
                visible: false
            }

            ShaderEffect {
                anchors.fill: parent

                readonly property var fromSource: fromTexture
                readonly property var toSource: toTexture
                readonly property real progress: preview.progress
                readonly property real aspect: width / Math.max(1, height)
                readonly property size resolution: Qt.size(width * Screen.devicePixelRatio, height * Screen.devicePixelRatio)

                fragmentShader: preview.shaderDir + preview.kind + ".frag.qsb"
            }
        }
    }
}
