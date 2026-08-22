import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "io.github.olivoil.omakeyd"

  property var snapshot: ({})
  property bool backendReady: false
  property bool backendBusy: false
  property string backendError: ""
  property bool refreshPending: false

  readonly property string backendCommand: {
    var url = String(Qt.resolvedUrl("bin/omakeyd"))
    return decodeURIComponent(url.replace(/^file:\/\//, ""))
  }
  readonly property var keyboards: Array.isArray(snapshot.keyboards) ? snapshot.keyboards : []
  readonly property var favorites: Array.isArray(snapshot.favorites) ? snapshot.favorites : []
  readonly property string selectedDevice: String(snapshot.selectedDevice || "")
  readonly property var currentKeyboard: {
    for (var i = 0; i < keyboards.length; i++)
      if (String(keyboards[i].name) === selectedDevice) return keyboards[i]
    return keyboards.length > 0 ? keyboards[0] : null
  }
  readonly property string indicatorText: currentKeyboard
    ? String(currentKeyboard.effectiveBrief || "KB") : "KB"
  readonly property string indicatorTooltip: {
    if (backendError) return "Omakeyd\n" + backendError
    if (!currentKeyboard) return "Omakeyd\nNo typing keyboard found"
    var lines = [
      String(currentKeyboard.effectiveName || "Unknown layout"),
      String(currentKeyboard.label || currentKeyboard.name)
    ]
    if (String(currentKeyboard.rawKeymap || "")
        && String(currentKeyboard.rawKeymap) !== String(currentKeyboard.effectiveName || ""))
      lines.push("XKB: " + String(currentKeyboard.rawKeymap))
    if (currentKeyboard.mappingDetail) lines.push(String(currentKeyboard.mappingDetail))
    return lines.join("\n")
  }
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function refresh() {
    if (snapshotProcess.running) {
      refreshPending = true
      return
    }
    refreshPending = false
    snapshotProcess.command = [backendCommand, "snapshot", "--limit", "24"]
    snapshotProcess.running = true
  }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
    if ("backendCommand" in target) target.backendCommand = root.backendCommand
  }

  function togglePanel() {
    if (panelLoader.item && panelLoader.item.toggle) panelLoader.item.toggle()
  }

  function open() {
    if (panelLoader.item && panelLoader.item.open) panelLoader.item.open()
  }

  function close() {
    if (panelLoader.item && panelLoader.item.close) panelLoader.item.close()
  }

  function favoriteMatchesKeyboard(favorite, keyboard) {
    if (!favorite || !keyboard) return false
    return String(favorite.layout || "") === String(keyboard.effectiveLayout || "")
      && String(favorite.variant || "") === String(keyboard.effectiveVariant || "")
  }

  function cycleFavorite(direction) {
    if (!currentKeyboard || favorites.length < 2 || applyProcess.running) return
    var current = -1
    for (var i = 0; i < favorites.length; i++) {
      if (favoriteMatchesKeyboard(favorites[i], currentKeyboard)) {
        current = i
        break
      }
    }
    if (current < 0) current = 0
    var next = (current + direction + favorites.length) % favorites.length
    var favorite = favorites[next]
    applyProcess.command = [
      backendCommand, "apply",
      "--device", selectedDevice,
      "--layout", String(favorite.layout || ""),
      "--variant", String(favorite.variant || ""),
      "--name", String(favorite.name || ""),
      "--brief", String(favorite.brief || "")
    ]
    backendBusy = true
    applyProcess.running = true
  }

  Component.onCompleted: refresh()
  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  Connections {
    target: Hyprland
    function onRawEvent(event) {
      if (!event) return
      var name = String(event.name || "")
      if (name === "activelayout" || name === "configreloaded") refreshTimer.restart()
    }
  }

  Timer {
    id: refreshTimer
    interval: 420
    onTriggered: root.refresh()
  }

  Timer {
    interval: 12000
    repeat: true
    running: true
    onTriggered: root.refresh()
  }

  Process {
    id: snapshotProcess
    stdout: StdioCollector {
      id: snapshotOutput
      waitForEnd: true
    }
    onExited: function(exitCode) {
      root.backendReady = true
      try {
        var payload = JSON.parse(String(snapshotOutput.text || "{}"))
        if (exitCode === 0 && payload.ok === true) {
          root.snapshot = payload
          root.backendError = ""
          root.injectPanel()
        } else {
          root.backendError = payload.error ? String(payload.error.message || "Backend unavailable") : "Backend unavailable"
        }
      } catch (error) {
        root.backendError = "Backend returned invalid data"
      }
      if (root.refreshPending) Qt.callLater(root.refresh)
    }
  }

  Process {
    id: applyProcess
    stdout: StdioCollector { waitForEnd: true }
    onExited: function() {
      root.backendBusy = false
      refreshTimer.restart()
    }
  }

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  IpcHandler {
    target: root.moduleName

    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.togglePanel() }
    function next(): void { root.cycleFavorite(1) }
    function previous(): void { root.cycleFavorite(-1) }
    function refresh(): void { root.refresh() }
    function status(): string { return JSON.stringify(root.snapshot) }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.indicatorText
    fontSize: Style.font.caption
    horizontalMargin: 7
    active: root.backendBusy
    dimmed: root.backendReady && (root.backendError !== "" || root.currentKeyboard === null)
    tooltipText: root.indicatorTooltip
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) root.cycleFavorite(1)
      else if (buttonCode === Qt.MiddleButton) root.cycleFavorite(-1)
      else root.togglePanel()
    }
    onWheelMoved: function(delta) { root.cycleFavorite(delta < 0 ? 1 : -1) }
  }
}
