.pragma library

var PRESETS = [5, 15, 30, 60, 180, 360, 720, 1440]

var ORDERS = [
    { value: "random", text: "Random" },
    { value: "name", text: "By name" }
]

var TRANSITIONS = [
    { value: "fade", text: "Fade" },
    { value: "slide", text: "Slide" },
    { value: "wipe", text: "Wipe" },
    { value: "grow", text: "Grow" },
    { value: "zoom", text: "Zoom" },
    { value: "pixelate", text: "Pixelate" },
    { value: "wave", text: "Wave" },
    { value: "random", text: "Random" }
]

function intervalLabel(minutes) {
    if (minutes < 60)
        return minutes + " min"
    var hours = Math.floor(minutes / 60)
    var rest = minutes % 60
    return rest === 0 ? hours + " h" : hours + " h " + rest + " min"
}

function durationLabel(ms) {
    return (ms / 1000).toFixed(1) + " s"
}
