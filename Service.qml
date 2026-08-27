import QtQuick
import Quickshell
import Quickshell.Io

// keyd owns persistent layout state in its root-owned profile. The service
// keeps a lightweight diagnostic endpoint without replaying input mutations.
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

  Timer {
    id: initialRefresh
    interval: 900
    onTriggered: root.refresh()
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
