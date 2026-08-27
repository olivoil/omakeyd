import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "io.github.olivoil.omakeyd"
  ipcTarget: "io.github.olivoil.omakeyd.panel"

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root
  property string backendCommand: "omakeyd"
  property var snapshot: ({})
  property bool busy: false
  property bool refreshing: false
  property string notice: ""
  property bool noticeError: false
  property string pendingAction: ""
  property string view: "home"

  property string editorId: ""
  property string editorName: ""
  property string editorBrief: ""
  property var editorRows: [
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";"],
    ["z", "x", "c", "v", "b", "n", "m", ",", ".", "/"]
  ]
  property var editorStartRows: []
  property var editorHistory: []
  property var editorFuture: []
  property int editorRow: 0
  property int editorColumn: 0

  readonly property color contentForeground: bar ? bar.foreground : Color.foreground
  readonly property color contentUrgent: bar ? bar.urgent : Color.urgent
  readonly property color contentDim: Qt.darker(contentForeground, 1.5)
  readonly property string contentFontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property var profiles: Array.isArray(snapshot.profiles) ? snapshot.profiles : []
  readonly property var layouts: Array.isArray(snapshot.layouts) ? snapshot.layouts : []
  readonly property string selectedProfileId: String(snapshot.selectedProfile || "")
  readonly property var selectedProfile: {
    for (var i = 0; i < profiles.length; i++)
      if (String(profiles[i].id) === selectedProfileId) return profiles[i]
    return profiles.length > 0 ? profiles[0] : null
  }
  readonly property var currentLayout: {
    if (!selectedProfile) return layouts.length > 0 ? layouts[0] : null
    for (var i = 0; i < layouts.length; i++)
      if (String(layouts[i].id) === String(selectedProfile.currentLayoutId || ""))
        return layouts[i]
    return layouts.length > 0 ? layouts[0] : null
  }
  readonly property var configuredLayout: {
    if (!selectedProfile) return null
    for (var i = 0; i < layouts.length; i++)
      if (String(layouts[i].id) === String(selectedProfile.configuredLayoutId || ""))
        return layouts[i]
    return null
  }
  readonly property var profileOptions: {
    var result = []
    for (var i = 0; i < profiles.length; i++) {
      var profile = profiles[i]
      result.push({
        value: String(profile.id || ""),
        label: String(profile.label || profile.id || "Unknown profile"),
        description: profile.ready
          ? String(profile.currentName || "Ready") : "Setup required"
      })
    }
    return result
  }

  function cloneRows(rows) {
    var result = []
    for (var row = 0; row < rows.length; row++) {
      var copy = []
      for (var column = 0; column < rows[row].length; column++)
        copy.push(String(rows[row][column]))
      result.push(copy)
    }
    return result
  }

  function qwertyRows() {
    return [
      ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
      ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";"],
      ["z", "x", "c", "v", "b", "n", "m", ",", ".", "/"]
    ]
  }

  function normalizeAssignment(value) {
    var text = String(value || "").trim().toLowerCase()
    var aliases = {
      "semicolon": ";",
      "comma": ",",
      "period": ".",
      "slash": "/"
    }
    if (aliases[text]) text = aliases[text]
    var allowed = "qwertyuiopasdfghjkl;zxcvbnm,./"
    return text.length === 1 && allowed.indexOf(text) >= 0 ? text : ""
  }

  function pushEditorHistory() {
    var history = editorHistory.slice(0)
    history.push(cloneRows(editorRows))
    editorHistory = history
    editorFuture = []
  }

  function selectEditorKey(row, column) {
    editorRow = row
    editorColumn = column
    keyAssignment.text = String(editorRows[row][column])
    keyAssignment.selectAll()
    keyAssignment.forceActiveFocus()
  }

  function assignEditorKey(value) {
    var requested = normalizeAssignment(value)
    if (!requested) {
      notice = "Choose one letter or one of ; , . /"
      noticeError = true
      return
    }
    var current = String(editorRows[editorRow][editorColumn])
    if (requested === current) return
    var otherRow = -1
    var otherColumn = -1
    for (var row = 0; row < editorRows.length; row++) {
      for (var column = 0; column < editorRows[row].length; column++) {
        if (String(editorRows[row][column]) === requested) {
          otherRow = row
          otherColumn = column
        }
      }
    }
    if (otherRow < 0) return
    pushEditorHistory()
    var updated = cloneRows(editorRows)
    updated[editorRow][editorColumn] = requested
    updated[otherRow][otherColumn] = current
    editorRows = updated
    notice = ""
    noticeError = false
    var next = editorColumn + 1
    if (next < 10) selectEditorKey(editorRow, next)
    else if (editorRow < 2) selectEditorKey(editorRow + 1, 0)
  }

  function undoEditor() {
    if (editorHistory.length === 0) return
    var history = editorHistory.slice(0)
    var previous = history.pop()
    var future = editorFuture.slice(0)
    future.push(cloneRows(editorRows))
    editorHistory = history
    editorFuture = future
    editorRows = cloneRows(previous)
    selectEditorKey(editorRow, editorColumn)
  }

  function redoEditor() {
    if (editorFuture.length === 0) return
    var future = editorFuture.slice(0)
    var next = future.pop()
    var history = editorHistory.slice(0)
    history.push(cloneRows(editorRows))
    editorHistory = history
    editorFuture = future
    editorRows = cloneRows(next)
    selectEditorKey(editorRow, editorColumn)
  }

  function resetEditor() {
    pushEditorHistory()
    editorRows = cloneRows(editorStartRows.length === 3 ? editorStartRows : qwertyRows())
    selectEditorKey(0, 0)
  }

  function beginEditor(layout, editExisting) {
    var base = layout && Array.isArray(layout.rows) ? layout.rows : qwertyRows()
    editorRows = cloneRows(base)
    editorStartRows = cloneRows(base)
    editorHistory = []
    editorFuture = []
    editorRow = 0
    editorColumn = 0
    editorId = editExisting && layout ? String(layout.id || "") : ""
    editorName = editExisting && layout ? String(layout.name || "") : ""
    editorBrief = editExisting && layout ? String(layout.brief || "") : ""
    notice = ""
    noticeError = false
    view = "editor"
    Qt.callLater(function() {
      editorNameField.text = root.editorName
      editorBriefField.text = root.editorBrief
      root.selectEditorKey(0, 0)
    })
  }

  function open() {
    root.controller.show()
    refresh()
    Qt.callLater(function() { panelFocus.forceActiveFocus() })
  }

  function close() {
    root.controller.hide()
    notice = ""
    view = "home"
  }

  function showSetup() {
    view = "setup"
    open()
  }

  function showStudio() {
    beginEditor(currentLayout, false)
    open()
  }

  function refresh() {
    if (snapshotProcess.running) return
    refreshing = true
    snapshotProcess.command = [backendCommand, "snapshot"]
    snapshotProcess.running = true
  }

  function parsePayload(text, exitCode) {
    var payload
    try {
      payload = JSON.parse(String(text || "{}"))
    } catch (error) {
      throw new Error("Omakeyd returned invalid data")
    }
    if (exitCode === 0 && payload.ok === true) return payload
    var message = payload.error ? String(payload.error.message || "Action failed") : "Action failed"
    var detail = payload.error ? String(payload.error.detail || "") : ""
    throw new Error(detail ? message + " " + detail : message)
  }

  function runAction(command, label) {
    if (actionProcess.running) return
    pendingAction = label
    notice = ""
    noticeError = false
    busy = true
    actionProcess.command = command
    actionProcess.running = true
  }

  function chooseProfile(profile) {
    runAction([backendCommand, "select-profile", "--profile", profile], "profile")
  }

  function applyLayout(layout) {
    if (!selectedProfile || !selectedProfile.canApply || !layout) return
    runAction([
      backendCommand, "apply",
      "--profile", selectedProfileId,
      "--layout-id", String(layout.id || "")
    ], "apply")
  }

  function setupProfile() {
    if (!selectedProfile) return
    runAction([
      backendCommand, "setup", "--profile", selectedProfileId
    ], "setup")
  }

  function saveEditor() {
    runAction([
      backendCommand, "layout-save",
      "--id", editorId,
      "--name", editorNameField.text,
      "--brief", editorBriefField.text,
      "--top", editorRows[0].join(" "),
      "--home", editorRows[1].join(" "),
      "--bottom", editorRows[2].join(" ")
    ], "save")
  }

  function removeLayout(layout) {
    if (!layout || !layout.removable) return
    runAction([
      backendCommand, "layout-remove", "--id", String(layout.id || "")
    ], "remove")
  }

  function layoutIsActive(layout) {
    return selectedProfile && layout
      && String(layout.id || "") === String(selectedProfile.currentLayoutId || "")
  }

  function diagnoseKeydCrash() {
    var crash = snapshot.keydCrash
    if (!crash || !snapshot.agentConfigured) return
    Quickshell.execDetached([
      "omarchy", "agent", "crash",
      String(crash.pid), String(crash.process || "keyd"),
      String(crash.executable || "/usr/bin/keyd"), String(crash.signal || "unknown")
    ])
    root.close()
  }

  onOpenedChanged: if (opened) refresh()

  Process {
    id: snapshotProcess
    stdout: StdioCollector {
      id: snapshotOutput
      waitForEnd: true
    }
    onExited: function(exitCode) {
      root.refreshing = false
      try {
        var payload = root.parsePayload(snapshotOutput.text, exitCode)
        root.snapshot = payload
        if (root.hostWidget) {
          root.hostWidget.snapshot = payload
          root.hostWidget.backendError = ""
        }
      } catch (error) {
        root.notice = error.message
        root.noticeError = true
      }
    }
  }

  Process {
    id: actionProcess
    stdout: StdioCollector {
      id: actionOutput
      waitForEnd: true
    }
    onExited: function(exitCode) {
      root.busy = false
      try {
        var payload = root.parsePayload(actionOutput.text, exitCode)
        root.notice = String(payload.message || "Done")
        root.noticeError = false
        if (root.pendingAction === "save" || root.pendingAction === "remove"
            || root.pendingAction === "setup")
          root.view = "home"
        root.refresh()
      } catch (error) {
        root.notice = error.message
        root.noticeError = true
      }
      root.pendingAction = ""
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: panelFocus
    contentWidth: panel.fittedContentWidth(Style.space(560))
    contentHeight: panel.fittedContentHeight(contentColumn.implicitHeight, Style.space(700))

    FocusScope {
      id: panelFocus
      anchors.fill: parent
      focus: true
      Keys.onEscapePressed: {
        if (root.view !== "home") root.view = "home"
        else root.close()
      }

      Flickable {
        id: panelScroll
        anchors.fill: parent
        contentWidth: width
        contentHeight: contentColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height

        Column {
          id: contentColumn
          width: panelScroll.width
          spacing: Style.space(14)

          RowLayout {
            visible: root.view !== "home"
            width: parent.width

            Button {
              iconText: "\uf060"
              text: "BACK"
              fontSize: Style.font.caption
              horizontalPadding: Style.space(8)
              verticalPadding: Style.space(5)
              onClicked: {
                root.view = "home"
                root.notice = ""
              }
            }

            Item { Layout.fillWidth: true }
          }

          PanelHero {
            width: parent.width
            title: root.view === "editor"
              ? (root.editorId ? "Edit layout" : "New layout")
              : root.view === "setup"
                ? "Connect Omakeyd to keyd"
                : root.view === "details"
                  ? "Keyd details"
                  : root.selectedProfile
                    ? String(root.selectedProfile.currentName || "Unknown layout")
                    : "No keyd profile"
            meta: root.view === "editor"
              ? "Visual positional editor"
              : root.selectedProfile
                ? String(root.selectedProfile.label || root.selectedProfile.id)
                : "Add a keyboard profile under /etc/keyd"
            detail: root.view === "home" && root.selectedProfile
              ? String(root.selectedProfile.currentBrief || "KB") : ""
            foreground: root.contentForeground
            fontFamily: root.contentFontFamily
            iconComponent: Component {
              Text {
                text: "\uf11c"
                color: root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.display
              }
            }
          }

          Column {
            visible: root.view === "home"
            width: parent.width
            spacing: Style.space(12)

            Column {
              visible: root.profiles.length > 1
              width: parent.width
              spacing: Style.space(7)

              PanelSectionHeader {
                text: "KEYD PROFILE"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
              }

              SearchableDropdown {
                id: profilePicker
                width: parent.width
                showLabel: false
                value: root.selectedProfileId
                options: root.profileOptions
                placeholderText: "Choose a keyd profile..."
                emptyText: "No keyd profiles"
                foreground: root.contentForeground
                onChanged: function(value) { root.chooseProfile(value) }
              }
            }

            Text {
              visible: root.profiles.length === 0
              width: parent.width
              text: "Omakeyd could not find a keyd device profile. keyd profiles normally live in /etc/keyd and contain an [ids] section."
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.WordWrap
            }

            Column {
              visible: root.selectedProfile && root.snapshot.keydActive === false
              width: parent.width
              spacing: Style.space(8)

              PanelSeparator { foreground: root.contentForeground }

              PanelSectionHeader {
                text: "KEYD IS STOPPED"
                foreground: root.contentUrgent
                fontFamily: root.contentFontFamily
              }

              Text {
                width: parent.width
                text: "Your saved layout is safe, but it is not active. Restart keyd to restore it."
                color: root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.body
                wrapMode: Text.WordWrap
              }

              RowLayout {
                width: parent.width
                spacing: Style.space(8)

                Button {
                  text: "RESTART KEYD"
                  selected: true
                  enabled: !root.busy && root.configuredLayout !== null
                  fontSize: Style.font.caption
                  horizontalPadding: Style.space(10)
                  verticalPadding: Style.space(6)
                  onClicked: root.applyLayout(root.configuredLayout)
                }

                Button {
                  visible: root.snapshot.keydCrash !== null && root.snapshot.keydCrash !== undefined
                  text: "DIAGNOSE WITH AI"
                  enabled: root.snapshot.agentConfigured === true
                  tooltipText: enabled
                    ? "Open this crash in your default Omarchy agent"
                    : "Choose a default agent in Omarchy first"
                  fontSize: Style.font.caption
                  horizontalPadding: Style.space(10)
                  verticalPadding: Style.space(6)
                  onClicked: root.diagnoseKeydCrash()
                }
              }

              Text {
                visible: root.snapshot.keydCrash !== null
                  && root.snapshot.keydCrash !== undefined
                  && root.snapshot.agentConfigured !== true
                width: parent.width
                text: "A keyd crash was recorded. Choose a default agent under Omarchy Setup to enable AI diagnosis."
                color: root.contentDim
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WordWrap
              }
            }

            Column {
              visible: root.selectedProfile && root.selectedProfile.needsSetup
              width: parent.width
              spacing: Style.space(9)

              PanelSeparator { foreground: root.contentForeground }

              PanelSectionHeader {
                text: "SETUP REQUIRED"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
              }

              Text {
                width: parent.width
                text: root.selectedProfile ? String(root.selectedProfile.setupReason || "One-time setup is required.") : ""
                color: root.contentForeground
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.body
                wrapMode: Text.WordWrap
              }

              Text {
                width: parent.width
                text: "Your current mapping stays active. Review the exact migration before authenticating once."
                color: root.contentDim
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WordWrap
              }

              Button {
                text: "REVIEW SETUP"
                selected: true
                enabled: !root.busy
                fontSize: Style.font.caption
                horizontalPadding: Style.space(10)
                verticalPadding: Style.space(6)
                onClicked: root.view = "setup"
              }
            }

            Column {
              visible: root.selectedProfile && root.selectedProfile.ready
              width: parent.width
              spacing: Style.space(7)

              PanelSeparator { foreground: root.contentForeground }

              PanelSectionHeader {
                text: "MY LAYOUTS"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
              }

              Repeater {
                model: root.layouts

                delegate: Column {
                  id: layoutRow
                  required property var modelData
                  width: contentColumn.width
                  spacing: 0

                  Rectangle {
                    width: parent.width
                    height: Style.space(50)
                    radius: Style.cornerRadius
                    color: root.layoutIsActive(layoutRow.modelData)
                      ? Style.selectedFillFor(root.contentForeground, Color.accent)
                      : "transparent"

                    RowLayout {
                      anchors.fill: parent
                      anchors.leftMargin: Style.space(9)
                      anchors.rightMargin: Style.space(5)
                      spacing: Style.space(8)

                      Text {
                        text: String(layoutRow.modelData.brief || "KB")
                        color: root.layoutIsActive(layoutRow.modelData) ? Color.accent : root.contentDim
                        font.family: root.contentFontFamily
                        font.pixelSize: Style.font.caption
                        font.bold: true
                        Layout.preferredWidth: Style.space(30)
                      }

                      Column {
                        Layout.fillWidth: true
                        spacing: Style.space(1)

                        Text {
                          width: parent.width
                          text: String(layoutRow.modelData.name || "Unnamed layout")
                          color: root.contentForeground
                          font.family: root.contentFontFamily
                          font.pixelSize: Style.font.body
                          font.bold: root.layoutIsActive(layoutRow.modelData)
                          elide: Text.ElideRight
                        }

                        Text {
                          width: parent.width
                          text: root.layoutIsActive(layoutRow.modelData)
                            ? "Current" : String(layoutRow.modelData.source || "saved")
                          color: root.contentDim
                          font.family: root.contentFontFamily
                          font.pixelSize: Style.font.caption
                          elide: Text.ElideRight
                        }
                      }

                      Button {
                        visible: !!layoutRow.modelData.editable
                        iconText: "\uf044"
                        tooltipText: "Edit layout"
                        enabled: !root.busy
                        horizontalPadding: Style.space(7)
                        verticalPadding: Style.space(5)
                        onClicked: root.beginEditor(layoutRow.modelData, true)
                      }

                      Button {
                        visible: !!layoutRow.modelData.removable
                        iconText: "\uf1f8"
                        tooltipText: "Remove layout"
                        enabled: !root.busy && !root.layoutIsActive(layoutRow.modelData)
                        horizontalPadding: Style.space(7)
                        verticalPadding: Style.space(5)
                        onClicked: root.removeLayout(layoutRow.modelData)
                      }

                      Button {
                        text: root.layoutIsActive(layoutRow.modelData) ? "CURRENT" : "SWITCH"
                        selected: root.layoutIsActive(layoutRow.modelData)
                        enabled: !root.busy && !!root.selectedProfile && root.selectedProfile.canApply
                          && !root.layoutIsActive(layoutRow.modelData)
                        fontSize: Style.font.caption
                        horizontalPadding: Style.space(8)
                        verticalPadding: Style.space(5)
                        onClicked: root.applyLayout(layoutRow.modelData)
                      }
                    }
                  }

                  PanelSeparator {
                    width: parent.width
                    foreground: root.contentForeground
                    strength: 0.07
                  }
                }
              }

              RowLayout {
                width: parent.width
                spacing: Style.space(8)

                Button {
                  iconText: "\uf067"
                  text: "NEW LAYOUT"
                  enabled: !root.busy
                  fontSize: Style.font.caption
                  horizontalPadding: Style.space(9)
                  verticalPadding: Style.space(6)
                  onClicked: root.beginEditor(root.currentLayout, false)
                }

                Item { Layout.fillWidth: true }

                Button {
                  iconText: "\uf05a"
                  tooltipText: "Keyd details"
                  enabled: !root.busy
                  horizontalPadding: Style.space(7)
                  verticalPadding: Style.space(6)
                  onClicked: root.view = "details"
                }
              }
            }
          }

          Column {
            visible: root.view === "setup"
            width: parent.width
            spacing: Style.space(11)

            PanelSectionHeader {
              text: "ONE-TIME KEYD SETUP"
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
            }

            Text {
              width: parent.width
              text: root.selectedProfile && root.selectedProfile.ready
                ? "Omakeyd will reinstall its constrained root-owned helper. The existing managed keyd profile and active layout will not change."
                : "Omakeyd will preserve the layout you are using now, add one managed keyd letter layer, and make a timestamped backup beside the original file."
              color: root.contentForeground
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.WordWrap
            }

            Text {
              width: parent.width
              text: root.selectedProfile ? String(root.selectedProfile.configPath || "") : ""
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WrapAnywhere
            }

            Text {
              width: parent.width
              text: "Authentication is requested once. Routine switches then use a root-owned helper that accepts only a complete permutation of the 30 letter and punctuation keys—no commands, macros, or arbitrary file paths."
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.WordWrap
            }

            Text {
              width: parent.width
              text: "XKB remains US. Omakeyd will not add you to keyd's privileged socket group."
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }

            Button {
              text: root.busy && root.pendingAction === "setup" ? "SETTING UP..." : "AUTHENTICATE & SET UP"
              selected: true
              enabled: !root.busy && root.selectedProfile
                && root.snapshot.helper && root.snapshot.helper.setupAvailable
              fontSize: Style.font.caption
              horizontalPadding: Style.space(10)
              verticalPadding: Style.space(6)
              onClicked: root.setupProfile()
            }
          }

          Column {
            visible: root.view === "editor"
            width: parent.width
            spacing: Style.space(12)

            PanelSectionHeader {
              text: "LAYOUT DETAILS"
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
            }

            RowLayout {
              width: parent.width
              spacing: Style.space(8)

              TextField {
                id: editorNameField
                Layout.fillWidth: true
                placeholderText: "Layout name"
                foreground: root.contentForeground
              }

              TextField {
                id: editorBriefField
                Layout.preferredWidth: Style.space(78)
                placeholderText: "Code"
                foreground: root.contentForeground
              }
            }

            PanelSeparator { foreground: root.contentForeground }

            RowLayout {
              width: parent.width

              PanelSectionHeader {
                text: "KEYBOARD"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
                Layout.fillWidth: true
              }

              Button {
                text: "UNDO"
                enabled: root.editorHistory.length > 0
                fontSize: Style.font.caption
                horizontalPadding: Style.space(7)
                verticalPadding: Style.space(4)
                onClicked: root.undoEditor()
              }

              Button {
                text: "REDO"
                enabled: root.editorFuture.length > 0
                fontSize: Style.font.caption
                horizontalPadding: Style.space(7)
                verticalPadding: Style.space(4)
                onClicked: root.redoEditor()
              }

              Button {
                text: "RESET"
                fontSize: Style.font.caption
                horizontalPadding: Style.space(7)
                verticalPadding: Style.space(4)
                onClicked: root.resetEditor()
              }
            }

            Column {
              width: parent.width
              spacing: Style.space(6)

              Repeater {
                model: 3

                delegate: Row {
                  id: keyRow
                  required property int index
                  property int rowIndex: index
                  anchors.horizontalCenter: parent.horizontalCenter
                  spacing: Style.space(5)

                  Repeater {
                    model: root.editorRows[keyRow.rowIndex]

                    delegate: Button {
                      required property int index
                      required property var modelData
                      width: Style.space(42)
                      height: Style.space(38)
                      text: String(modelData).toUpperCase()
                      selected: root.editorRow === keyRow.rowIndex && root.editorColumn === index
                      fontSize: Style.font.body
                      horizontalPadding: 0
                      verticalPadding: 0
                      onClicked: root.selectEditorKey(keyRow.rowIndex, index)
                    }
                  }
                }
              }
            }

            Text {
              width: parent.width
              text: "Select a keycap, then type the key it should produce. Assigning a key already in use swaps the two positions, so the layout always stays valid."
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }

            RowLayout {
              width: parent.width
              spacing: Style.space(8)

              TextField {
                id: keyAssignment
                Layout.fillWidth: true
                placeholderText: "Type q–z or ; , . /"
                foreground: root.contentForeground
                onAccepted: root.assignEditorKey(text)
              }

              Button {
                text: "ASSIGN"
                selected: true
                fontSize: Style.font.caption
                horizontalPadding: Style.space(9)
                verticalPadding: Style.space(6)
                onClicked: root.assignEditorKey(keyAssignment.text)
              }
            }

            Button {
              text: root.busy && root.pendingAction === "save" ? "SAVING..." : "SAVE LAYOUT"
              selected: true
              enabled: !root.busy && editorNameField.text.trim() !== ""
              fontSize: Style.font.caption
              horizontalPadding: Style.space(10)
              verticalPadding: Style.space(6)
              onClicked: root.saveEditor()
            }
          }

          Column {
            visible: root.view === "details"
            width: parent.width
            spacing: Style.space(9)

            PanelSectionHeader {
              text: "KEYD INTEGRATION"
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
            }

            Text {
              width: parent.width
              text: root.selectedProfile
                ? "Profile: " + String(root.selectedProfile.id || "")
                  + "\nManaged layer: " + String(root.selectedProfile.managedLayer || "")
                  + "\nConfig: " + String(root.selectedProfile.configPath || "")
                : "No selected profile"
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WrapAnywhere
            }

            Text {
              width: parent.width
              text: root.snapshot.helper
                ? "Helper: " + (root.snapshot.helper.installed ? "installed" : "not installed")
                  + "\n" + String(root.snapshot.helper.path || "")
                : "Helper status unavailable"
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WrapAnywhere
            }

            Text {
              width: parent.width
              text: "Routine switching rewrites only the marked 30-key layer, validates it with keyd check, restarts keyd, and rolls back if keyd does not stay healthy."
              color: root.contentForeground
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.WordWrap
            }
          }

          Text {
            visible: root.notice !== ""
            width: parent.width
            text: root.notice
            color: root.noticeError ? root.contentUrgent : root.contentForeground
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.body
            font.bold: root.noticeError
            wrapMode: Text.WordWrap
          }

          Text {
            visible: root.refreshing || root.busy
            width: parent.width
            text: root.busy
              ? (root.pendingAction === "apply" ? "Switching keyd layout..." : "Working...")
              : "Reading keyd profiles..."
            color: root.contentDim
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
        }
      }
    }
  }
}
