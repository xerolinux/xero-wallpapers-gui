import QtQuick
import QtMultimedia

Item {
    id: thumb

    property url source
    property bool done: false

    // Emits null when no frame could be captured.
    signal grabbed(var result)

    function finish(result) {
        if (done)
            return
        done = true
        player.stop()
        grabbed(result)
    }

    MediaPlayer {
        id: player

        source: thumb.source
        videoOutput: output
        onSourceChanged: if (player.source.toString() !== "") player.play()
        onErrorOccurred: thumb.finish(null)
        onPositionChanged: () => {
            if (thumb.done || player.position <= 0 || player.playbackState !== MediaPlayer.PlayingState)
                return
            player.pause()
            const frame = output.sourceRect
            if (frame.width > 0 && frame.height > 0) {
                const k = Math.min(thumb.width / frame.width, thumb.height / frame.height)
                output.width = Math.round(frame.width * k)
                output.height = Math.round(frame.height * k)
            }
            if (!output.grabToImage(result => thumb.finish(result)))
                thumb.finish(null)
        }
    }

    VideoOutput {
        id: output
        anchors.centerIn: parent
        width: thumb.width
        height: thumb.height
        fillMode: VideoOutput.PreserveAspectFit
    }

    Timer {
        interval: 8000
        running: !thumb.done
        onTriggered: thumb.finish(null)
    }
}
