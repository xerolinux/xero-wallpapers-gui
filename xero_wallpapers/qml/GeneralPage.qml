import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import "." as App
import "Slideshow.js" as Slide

QQC2.ScrollView {
    id: page

    property bool clearing: false
    property string freed: ""

    contentWidth: availableWidth
    QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff

    Connections {
        target: settings

        function onCacheCleared(size) {
            page.clearing = false
            page.freed = size
        }
    }

    ColumnLayout {
        width: page.availableWidth
        spacing: Kirigami.Units.largeSpacing

        App.SettingsParts.PageHeader {
            Layout.margins: Kirigami.Units.gridUnit
            Layout.bottomMargin: 0
            title: "General"
            lead: "Content, filters, automatic wallpaper changes, updates and the thumbnail cache."
        }

        App.SettingsParts.Group {
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.rightMargin: Kirigami.Units.gridUnit

            App.SettingsParts.Row {
                separator: false
                title: "Safe content only"
                subtitle: settings.safeContent ? "Wallhaven shows safe-for-work images only"
                    : "Wallhaven also shows sketchy images. NSFW is never shown."

                QQC2.Switch {
                    checked: settings.safeContent
                    onToggled: settings.safeContent = checked
                }
            }

            App.SettingsParts.Row {
                title: "Match my screen"
                subtitle: "Start with wallpapers that exactly match your primary screen's resolution"

                QQC2.Switch {
                    checked: settings.matchScreen
                    onToggled: settings.matchScreen = checked
                }
            }

            App.SettingsParts.Row {
                title: "Hide duplicates"
                subtitle: "Show each picture once while browsing and in the Library, keeping the largest copy"

                QQC2.Switch {
                    checked: settings.hideDuplicates
                    onToggled: settings.hideDuplicates = checked
                }
            }
        }

        App.SettingsParts.Group {
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.rightMargin: Kirigami.Units.gridUnit

            App.SettingsParts.Row {
                separator: false
                enabled: settings.slideshowAvailable
                title: "Change wallpaper automatically"
                subtitle: !settings.slideshowAvailable ? settings.slideshowReason
                    : "Cycles through your Wallpapers folder, even when the app is closed"

                QQC2.BusyIndicator {
                    Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                    Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                    visible: settings.slideshowBusy
                    running: visible
                }

                QQC2.Switch {
                    id: slideSwitch

                    checked: settings.slideshowEnabled
                    enabled: !settings.slideshowBusy && (checked || settings.slideshowFolderProblem === "")
                    onToggled: settings.slideshowEnabled = checked

                    Connections {
                        target: settings

                        function onSlideshowChanged() {
                            if (!settings.slideshowBusy)
                                slideSwitch.checked = settings.slideshowEnabled
                        }
                    }
                }
            }

            Kirigami.InlineMessage {
                Layout.fillWidth: true
                Layout.margins: Kirigami.Units.largeSpacing
                Layout.topMargin: 0
                visible: settings.slideshowAvailable && settings.slideshowFolderProblem !== ""
                type: Kirigami.MessageType.Warning
                text: settings.slideshowFolderProblem
            }

            App.SettingsParts.Row {
                visible: settings.slideshowEnabled
                title: "Change every"
                subtitle: "How often the wallpaper changes"

                App.SlideshowParts.IntervalPicker {
                    minutes: settings.slideshowMinutes
                    onPicked: minutes => settings.slideshowMinutes = minutes
                }
            }

            App.SettingsParts.Row {
                visible: settings.slideshowEnabled
                title: "Order"
                subtitle: "Shuffle, or go through the folder by file name"

                App.SlideshowParts.ChoiceBox {
                    choices: Slide.ORDERS
                    value: settings.slideshowOrder
                    onPicked: value => settings.slideshowOrder = value
                }
            }

            App.SettingsParts.Row {
                visible: settings.slideshowEnabled
                title: "Transition"
                subtitle: "How one wallpaper turns into the next"
                leading: App.TransitionPreview {
                    transition: settings.slideshowTransition
                    duration: settings.slideshowTransitionMs
                    shaderDir: settings.slideshowShaderDir
                }

                App.SlideshowParts.ChoiceBox {
                    choices: Slide.TRANSITIONS
                    value: settings.slideshowTransition
                    onPicked: value => settings.slideshowTransition = value
                }
            }

            App.SettingsParts.Row {
                visible: settings.slideshowEnabled
                title: "Transition length"
                subtitle: "How long each transition takes"

                App.SlideshowParts.DurationPicker {
                    ms: settings.slideshowTransitionMs
                    onPicked: ms => settings.slideshowTransitionMs = ms
                }
            }
        }

        App.SettingsParts.Group {
            Layout.leftMargin: Kirigami.Units.gridUnit
            Layout.rightMargin: Kirigami.Units.gridUnit

            App.SettingsParts.Row {
                separator: false
                title: "Thumbnail cache size"
                subtitle: page.clearing ? "Clearing…" : page.freed !== "" ? "Freed " + page.freed
                    : "Older thumbnails are removed when the cache is full"

                App.CacheSizeBox {
                    value: settings.cacheSizeMb
                    onPicked: size => settings.cacheSizeMb = size
                }

                QQC2.Button {
                    text: "Clear cache"
                    icon.name: "edit-clear-all"
                    enabled: !page.clearing
                    onClicked: {
                        page.clearing = true
                        page.freed = ""
                        settings.clearCache()
                    }
                }
            }
        }
    }
}
