import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

// Per-device Hyprland settings are runtime state. Reapply the user's last
// layout after the shell and compositor configuration have loaded.
Item {
  id: root

  property var shell: null
  property var manifest: null
  property string lastResult: ""

  readonly property string backendCommand: {
    var source = manifest && manifest.__sourceDir ? String(manifest.__sourceDir) : ""
    return source ? source.replace(/\/$/, "") + "/bin/omakeyd" : "omakeyd"
  }

  function refresh() {
    if (statusProcess.running) return
    statusProcess.command = [backendCommand, "restore"]
    statusProcess.running = true
  }

  Component.onCompleted: initialRefresh.restart()
  Component.onDestruction: Quickshell.execDetached([backendCommand, "reset"])

  Timer {
    id: initialRefresh
    interval: 900
    onTriggered: root.refresh()
  }

  Connections {
    target: Hyprland
    function onRawEvent(event) {
      if (event && event.name === "configreloaded") initialRefresh.restart()
    }
  }

  Process {
    id: statusProcess
    stdout: StdioCollector {
      id: statusOutput
      waitForEnd: true
    }
    onExited: root.lastResult = String(statusOutput.text || "")
  }

  IpcHandler {
    target: "io.github.olivoil.omakeyd.service"

    function restore(): void { root.refresh() }
    function refresh(): void { root.refresh() }
    function status(): string { return root.lastResult }
  }
}
