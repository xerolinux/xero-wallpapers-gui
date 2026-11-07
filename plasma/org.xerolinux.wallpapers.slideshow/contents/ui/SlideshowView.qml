import QtQuick
import Qt.labs.folderlistmodel

Item {
    id: view

    property string folder
    property int interval: 3600
    property int order: 0
    property string transition: "fade"
    property int duration: 1200
    property int fillMode: Image.PreserveAspectCrop
    property size sourceSize: Qt.size(width * Screen.devicePixelRatio, height * Screen.devicePixelRatio)

    readonly property bool naturalSize: fillMode === Image.Pad || fillMode === Image.Tile
        || fillMode === Image.TileVertically || fillMode === Image.TileHorizontally
    readonly property url currentSource: front.status === Image.Ready ? front.source : ""
    readonly property bool transitioning: anim.running
    readonly property var kinds: ["fade", "slide", "wipe", "grow", "zoom", "pixelate", "wave"]
    readonly property var shaderKinds: ["wipe", "grow", "pixelate", "wave"]
    property string activeKind: ""
    property real progress: 0

    property Image front: imageA
    property Image back: imageB
    property int pendingSlot: 0
    property var broken: ({})
    property bool folderSwitched: false

    signal shown()
    signal switched()

    clip: true

    function folderUrl(path) {
        if (!path)
            return "";
        return path.startsWith("file:") ? path : "file://" + path.split("/").map(encodeURIComponent).join("/");
    }

    function reload() {
        folderSwitched = true;
        broken = {};
        files.folder = "";
        files.folder = folderUrl(folder);
        if (!folder)
            refresh();
    }

    function clockSlot() {
        return Math.floor(Date.now() / (Math.max(1, interval) * 1000));
    }

    // Timer is monotonic and stalls across suspend, so wake at least every minute and compare wall-clock slots.
    function schedule() {
        const ms = Math.max(1, interval) * 1000;
        ticker.interval = Math.min(60000, ms - (Date.now() % ms) + 50);
        ticker.restart();
    }

    function tick() {
        const slot = clockSlot();
        if (files.count === 0) {
            reload();
        } else if (slot !== pendingSlot) {
            if (slot % files.count === 0)
                broken = {};
            showSlot(slot, true);
        }
        schedule();
    }

    function permutation(cycle, count) {
        let seed = Math.imul(cycle | 0, 0x9E3779B1) ^ count;
        const next = () => {
            seed = (seed + 0x6D2B79F5) | 0;
            let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
        const p = [];
        for (let i = 0; i < count; i++)
            p.push(i);
        for (let i = count - 1; i > 0; i--) {
            const j = Math.floor(next() * (i + 1));
            [p[i], p[j]] = [p[j], p[i]];
        }
        return p;
    }

    // Slots come from the wall clock so every screen shows the same image without talking to each other.
    function indexFor(slot, count) {
        if (count < 2)
            return 0;
        const pos = ((slot % count) + count) % count;
        if (order === 1 || count === 2)
            return pos;
        const cycle = Math.floor(slot / count);
        const p = permutation(cycle, count);
        if (p[0] === permutation(cycle - 1, count)[count - 1])
            [p[0], p[1]] = [p[1], p[0]];
        return p[pos];
    }

    function showSlot(slot, animate) {
        if (files.count === 0 || anim.running || width <= 0 || height <= 0)
            return;
        pendingSlot = slot;
        const live = animate && front.status === Image.Ready;
        const valid = [];
        for (let i = 0; i < files.count; i++) {
            const candidate = String(files.get(i, "fileUrl"));
            if (!broken[candidate])
                valid.push(candidate);
        }
        if (valid.length === 0) {
            back.source = "";
            if (front.status !== Image.Ready) {
                front.source = "";
                shown();
            }
            return;
        }
        const url = valid[indexFor(slot, valid.length)];
        if (!live) {
            front.source = url;
            return;
        }
        if (url === String(front.source))
            return;
        back.source = "";
        back.source = url;
    }

    function skip(img) {
        broken[String(img.source)] = true;
        showSlot(pendingSlot, front.status === Image.Ready);
    }

    function refresh() {
        if (folder && files.status !== FolderListModel.Ready)
            return;
        if (files.count === 0 || !folder) {
            if (!anim.running) {
                front.source = "";
                back.source = "";
            }
            shown();
            return;
        }
        if (folderSwitched || front.source.toString() === "") {
            folderSwitched = false;
            showSlot(clockSlot(), front.status === Image.Ready);
        }
    }

    function imageStatus(img) {
        if (img.status === Image.Error)
            skip(img);
        else if (img.status === Image.Ready && img === back)
            begin();
        else if (img.status === Image.Ready) {
            shown();
            switched();
        }
    }

    function begin() {
        if (transition === "random") {
            const others = kinds.filter(k => k !== activeKind);
            activeKind = others[Math.floor(Math.random() * others.length)];
        } else {
            activeKind = kinds.indexOf(transition) >= 0 ? transition : "fade";
        }
        front.z = 1;
        back.z = 2;
        back.opacity = activeKind === "fade" || activeKind === "zoom" ? 0 : 1;
        progress = 0;
        applyProgress();
        anim.restart();
    }

    function applyProgress() {
        const p = progress;
        switch (activeKind) {
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
        for (const img of [front, back]) {
            img.x = 0;
            img.scale = 1;
        }
        front.opacity = 1;
        front.z = 1;
        back.opacity = 0;
        back.z = 0;
        back.source = "";
        switched();
    }

    onProgressChanged: applyProgress()
    onFolderChanged: reload()
    onIntervalChanged: schedule()
    onWidthChanged: if (front.source.toString() === "") refresh()
    onHeightChanged: if (front.source.toString() === "") refresh()
    Component.onCompleted: {
        reload();
        schedule();
    }

    FolderListModel {
        id: files
        nameFilters: ["*.jpg", "*.jpeg", "*.png", "*.webp"]
        caseSensitive: false
        showDirs: false
        showDotAndDotDot: false
        sortField: FolderListModel.Name
        onStatusChanged: view.refresh()
        onCountChanged: {
            view.broken = {};
            view.refresh();
        }
    }

    Timer {
        id: ticker
        onTriggered: view.tick()
    }

    NumberAnimation {
        id: anim
        target: view
        property: "progress"
        from: 0
        to: 1
        duration: Math.max(1, view.duration)
        easing.type: Easing.OutCubic
        onFinished: view.finish()
    }

    Image {
        id: imageA
        width: view.width
        height: view.height
        asynchronous: true
        cache: false
        fillMode: view.fillMode
        sourceSize: view.naturalSize ? undefined : view.sourceSize
        onStatusChanged: view.imageStatus(imageA)
    }

    Image {
        id: imageB
        width: view.width
        height: view.height
        opacity: 0
        asynchronous: true
        cache: false
        fillMode: view.fillMode
        sourceSize: view.naturalSize ? undefined : view.sourceSize
        onStatusChanged: view.imageStatus(imageB)
    }

    Loader {
        anchors.fill: parent
        z: 3
        active: view.transitioning && view.shaderKinds.indexOf(view.activeKind) >= 0
        sourceComponent: Item {
            ShaderEffectSource {
                id: fromTexture
                sourceItem: view.front
                hideSource: true
                visible: false
            }
            ShaderEffectSource {
                id: toTexture
                sourceItem: view.back
                hideSource: true
                visible: false
            }
            ShaderEffect {
                anchors.fill: parent
                readonly property var fromSource: fromTexture
                readonly property var toSource: toTexture
                readonly property real progress: view.progress
                readonly property real aspect: width / Math.max(1, height)
                readonly property size resolution: Qt.size(width * Screen.devicePixelRatio, height * Screen.devicePixelRatio)
                fragmentShader: Qt.resolvedUrl("shaders/" + view.activeKind + ".frag.qsb")
            }
        }
    }
}
