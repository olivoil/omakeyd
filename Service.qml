import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

// Reapplies only layouts the user has explicitly selected through Omakeyd.
// It never edits Hyprland or keyd configuration files.
Item {
  id: root

  property var shell: null
  property var manifest: null
  property bool restorePending: false
  property string lastResult: ""

  readonly property string backendCommand: {
    var source = manifest && manifest.__sourceDir ? String(manifest.__sourceDir) : ""
    return source ? source.replace(/\/$/, "") + "/bin/omakeyd" : "omakeyd"
  }

  function restore() {
    if (restoreProcess.running) {
      restorePending = true
      return
    }
    restorePending = false
    restoreProcess.command = [backendCommand, "restore"]
    restoreProcess.running = true
  }

  Component.onCompleted: initialRestore.restart()

  Connections {
    target: Hyprland
    function onRawEvent(event) {
      if (!event || String(event.name || "") !== "configreloaded") return
      // Let Hyprland finish rebuilding devices before restoring runtime choices.
      reloadRestore.restart()
    }
  }

  Timer {
    id: initialRestore
    interval: 900
    onTriggered: root.restore()
  }

  Timer {
    id: reloadRestore
    interval: 500
    onTriggered: root.restore()
  }

  Process {
    id: restoreProcess
    stdout: StdioCollector {
      id: restoreOutput
      waitForEnd: true
    }
    onExited: function() {
      root.lastResult = String(restoreOutput.text || "")
      if (root.restorePending) Qt.callLater(root.restore)
    }
  }

  IpcHandler {
    target: "io.github.olivoil.omakeyd.service"

    function restore(): void { root.restore() }
    function status(): string { return root.lastResult }
  }
}
