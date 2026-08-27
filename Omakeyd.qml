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
  readonly property var profiles: Array.isArray(snapshot.profiles) ? snapshot.profiles : []
  readonly property var layouts: Array.isArray(snapshot.layouts) ? snapshot.layouts : []
  readonly property string selectedProfile: String(snapshot.selectedProfile || "")
  readonly property var currentProfile: {
    for (var i = 0; i < profiles.length; i++)
      if (String(profiles[i].id) === selectedProfile) return profiles[i]
    return profiles.length > 0 ? profiles[0] : null
  }
  readonly property string indicatorText: "\uf11c"
    + (currentProfile ? "  " + String(currentProfile.currentBrief || "KB") : "")
  readonly property string indicatorTooltip: {
    if (backendError) return "Omakeyd\n" + backendError
    if (snapshot.keydConflict === true)
      return "Omakeyd\n" + String(snapshot.conflictMessage || "keyd is running")
    if (!currentProfile) return "Omakeyd\nNo keyboard found"
    var lines = [
      String(currentProfile.currentName || "Unknown layout"),
      String(currentProfile.label || currentProfile.id)
    ]
    return lines.join("\n")
  }
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property bool popoutSwitchClosing: panelLoader.item
    ? panelLoader.item.popoutSwitchClosing === true : false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function refresh() {
    if (snapshotProcess.running) {
      refreshPending = true
      return
    }
    refreshPending = false
    snapshotProcess.command = [backendCommand, "snapshot"]
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
    if ("snapshot" in target) target.snapshot = root.snapshot
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

  function closeForPopoutSwitch() {
    if (panelLoader.item && panelLoader.item.closeForPopoutSwitch)
      panelLoader.item.closeForPopoutSwitch()
  }

  function openStudio() {
    if (panelLoader.item && panelLoader.item.showStudio) panelLoader.item.showStudio()
  }

  function cycleLayout(direction) {
    if (!currentProfile || !currentProfile.canApply || layouts.length < 2 || applyProcess.running)
      return
    var current = 0
    for (var i = 0; i < layouts.length; i++) {
      if (String(layouts[i].id) === String(currentProfile.currentLayoutId || "")) {
        current = i
        break
      }
    }
    var next = (current + direction + layouts.length) % layouts.length
    applyProcess.command = [
      backendCommand, "apply",
      "--profile", selectedProfile,
      "--layout-id", String(layouts[next].id || "")
    ]
    backendBusy = true
    applyProcess.running = true
  }

  Component.onCompleted: refresh()
  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  Timer {
    id: refreshTimer
    interval: 300
    onTriggered: root.refresh()
  }

  Connections {
    target: Hyprland
    function onRawEvent(event) {
      if (!event || !event.name) return
      var name = String(event.name)
      if (name === "activelayout" || name === "configreloaded")
        refreshTimer.restart()
    }
  }

  Timer {
    interval: 10000
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
          root.backendError = payload.error
            ? String(payload.error.message || "Backend unavailable") : "Backend unavailable"
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
    onStatusChanged: {
      if (status === Loader.Error) {
        var detail = errorString && errorString() ? errorString() : "unknown QML error"
        console.warn("Omakeyd panel failed to load:", detail)
      }
    }
  }

  IpcHandler {
    target: root.moduleName

    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.togglePanel() }
    function next(): void { root.cycleLayout(1) }
    function previous(): void { root.cycleLayout(-1) }
    function refresh(): void { root.refresh() }
    function studio(): void { root.openStudio() }
    function status(): string { return JSON.stringify(root.snapshot) }
    function panelStatus(): string {
      return JSON.stringify({
        loaderStatus: panelLoader.status,
        hasItem: panelLoader.item !== null,
        opened: root.opened
      })
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.indicatorText
    fontSize: Style.font.caption
    horizontalMargin: 7
    active: root.opened || root.backendBusy
    dimmed: root.backendReady && (root.backendError !== "" || root.currentProfile === null
      || root.snapshot.keydConflict === true)
    tooltipText: root.indicatorTooltip
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) root.cycleLayout(1)
      else if (buttonCode === Qt.MiddleButton) root.cycleLayout(-1)
      else root.togglePanel()
    }
    onWheelMoved: function(delta) { root.cycleLayout(delta < 0 ? 1 : -1) }
  }
}
