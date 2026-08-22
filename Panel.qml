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
  property string backendCommand: "omakeyd"
  property var snapshot: ({})
  property var searchResults: []
  property string searchQuery: ""
  property bool busy: false
  property bool customExpanded: false
  property bool sourceExpanded: false
  property bool refreshing: false
  property string notice: ""
  property bool noticeError: false
  property string pendingAction: ""

  readonly property color contentForeground: bar ? bar.foreground : Color.foreground
  readonly property color contentUrgent: bar ? bar.urgent : Color.urgent
  readonly property color contentDim: Qt.darker(contentForeground, 1.5)
  readonly property string contentFontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property var keyboards: Array.isArray(snapshot.keyboards) ? snapshot.keyboards : []
  readonly property var favorites: Array.isArray(snapshot.favorites) ? snapshot.favorites : []
  readonly property string selectedDevice: String(snapshot.selectedDevice || "")
  readonly property var selectedKeyboard: {
    for (var i = 0; i < keyboards.length; i++)
      if (String(keyboards[i].name) === selectedDevice) return keyboards[i]
    return keyboards.length > 0 ? keyboards[0] : null
  }
  readonly property var deviceOptions: {
    var result = []
    for (var i = 0; i < keyboards.length; i++) {
      var keyboard = keyboards[i]
      result.push({
        value: String(keyboard.name || ""),
        label: String(keyboard.label || keyboard.name || "Unknown keyboard"),
        description: String(keyboard.effectiveName || "Unknown layout") + " · " + String(keyboard.name || "")
      })
    }
    return result
  }
  readonly property bool editorFocused: customName.activeFocus || customBrief.activeFocus
    || customBaseLayout.activeFocus || customBaseVariant.activeFocus
    || customTop.activeFocus || customHome.activeFocus || customBottom.activeFocus
    || sourceName.activeFocus || sourceTop.activeFocus || sourceHome.activeFocus
    || sourceBottom.activeFocus || layoutSearch.activeFocus

  function open() {
    root.controller.show()
    refresh()
    Qt.callLater(function() { if (devicePicker) devicePicker.forceActiveFocus() })
  }

  function close() {
    root.controller.hide()
    notice = ""
  }

  function refresh() {
    if (snapshotProcess.running) return
    refreshing = true
    snapshotProcess.command = [backendCommand, "snapshot", "--limit", "30"]
    snapshotProcess.running = true
  }

  function parsePayload(text, exitCode) {
    try {
      var payload = JSON.parse(String(text || "{}"))
      if (exitCode === 0 && payload.ok === true) return payload
      var message = payload.error ? String(payload.error.message || "Action failed") : "Action failed"
      var detail = payload.error ? String(payload.error.detail || "") : ""
      throw new Error(detail ? message + " " + detail : message)
    } catch (error) {
      if (error && error.message) throw error
      throw new Error("Omakeyd returned invalid data")
    }
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

  function chooseDevice(device) {
    runAction([backendCommand, "select-device", "--device", device], "device")
  }

  function applyLayout(layout) {
    if (!selectedKeyboard || !selectedKeyboard.canApply || !layout) return
    runAction([
      backendCommand, "apply",
      "--device", selectedDevice,
      "--layout", String(layout.layout || ""),
      "--variant", String(layout.variant || ""),
      "--name", String(layout.name || ""),
      "--brief", String(layout.brief || "")
    ], "apply")
  }

  function addLayout(layout) {
    if (!layout) return
    runAction([
      backendCommand, "favorite-add",
      "--layout", String(layout.layout || ""),
      "--variant", String(layout.variant || ""),
      "--name", String(layout.name || ""),
      "--brief", String(layout.brief || ""),
      "--source", String(layout.source || "system")
    ], "save")
  }

  function removeLayout(layout) {
    if (!layout) return
    runAction([backendCommand, "favorite-remove", "--id", String(layout.id || "")], "remove")
  }

  function saveCustom() {
    runAction([
      backendCommand, "custom-save",
      "--name", customName.text,
      "--brief", customBrief.text,
      "--base-layout", customBaseLayout.text,
      "--base-variant", customBaseVariant.text,
      "--top", customTop.text,
      "--home", customHome.text,
      "--bottom", customBottom.text
    ], "custom")
  }

  function sourceDefaultRow(index) {
    if (selectedKeyboard && selectedKeyboard.source && Array.isArray(selectedKeyboard.source.rows)
        && Array.isArray(selectedKeyboard.source.rows[index]))
      return selectedKeyboard.source.rows[index].join(" ")
    var defaults = [
      "q w e r t y u i o p",
      "a s d f g h j k l semicolon",
      "z x c v b n m comma period slash"
    ]
    return defaults[index]
  }

  function openSourceEditor() {
    sourceName.text = selectedKeyboard && selectedKeyboard.source
      ? String(selectedKeyboard.source.name || "Physical remap") : "Physical remap"
    sourceTop.text = sourceDefaultRow(0)
    sourceHome.text = sourceDefaultRow(1)
    sourceBottom.text = sourceDefaultRow(2)
    sourceExpanded = true
    Qt.callLater(function() { sourceName.forceActiveFocus() })
  }

  function saveSource() {
    if (!selectedKeyboard) return
    runAction([
      backendCommand, "source-save",
      "--device", selectedDevice,
      "--name", sourceName.text,
      "--top", sourceTop.text,
      "--home", sourceHome.text,
      "--bottom", sourceBottom.text
    ], "source")
  }

  function startSearch() {
    if (catalogProcess.running) {
      searchDebounce.restart()
      return
    }
    catalogProcess.command = [
      backendCommand, "catalog", "--query", searchQuery, "--limit", "32"
    ]
    catalogProcess.running = true
  }

  function layoutIsActive(layout) {
    if (!selectedKeyboard || !layout) return false
    return String(layout.layout || "") === String(selectedKeyboard.effectiveLayout || "")
      && String(layout.variant || "") === String(selectedKeyboard.effectiveVariant || "")
  }

  onOpenedChanged: if (opened) refresh()
  onSelectedDeviceChanged: {
    sourceExpanded = false
    if (selectedKeyboard && !selectedKeyboard.canApply)
      notice = String(selectedKeyboard.blockedReason || "This keyboard needs a source map before switching.")
  }

  Timer {
    id: searchDebounce
    interval: 180
    onTriggered: root.startSearch()
  }

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
        root.searchResults = Array.isArray(payload.catalog) ? payload.catalog : []
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
    id: catalogProcess
    stdout: StdioCollector {
      id: catalogOutput
      waitForEnd: true
    }
    onExited: function(exitCode) {
      try {
        var payload = root.parsePayload(catalogOutput.text, exitCode)
        root.searchResults = Array.isArray(payload.catalog) ? payload.catalog : []
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
        if (root.pendingAction === "custom") root.customExpanded = false
        if (root.pendingAction === "source") root.sourceExpanded = false
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
    owner: root
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: panelFocus
    contentWidth: panel.fittedContentWidth(Style.space(620))
    contentHeight: panel.fittedContentHeight(contentColumn.implicitHeight, Style.space(720))

    FocusScope {
      id: panelFocus
      anchors.fill: parent
      focus: true
      Keys.onEscapePressed: root.close()

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

          PanelHero {
            width: parent.width
            title: root.selectedKeyboard
              ? String(root.selectedKeyboard.effectiveName || "Unknown layout")
              : "No typing keyboard"
            meta: root.selectedKeyboard
              ? String(root.selectedKeyboard.label || root.selectedKeyboard.name)
              : "Connect a keyboard to continue"
            detail: root.selectedKeyboard ? String(root.selectedKeyboard.effectiveBrief || "") : ""
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
            width: parent.width
            spacing: Style.space(7)

            PanelSectionHeader {
              text: "TARGET KEYBOARD"
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
            }

            SearchableDropdown {
              id: devicePicker
              width: parent.width
              showLabel: false
              value: root.selectedDevice
              options: root.deviceOptions
              placeholderText: "Choose a keyboard..."
              emptyText: "No typing keyboards"
              foreground: root.contentForeground
              onChanged: function(value) { root.chooseDevice(value) }
            }

            Text {
              width: parent.width
              text: root.selectedKeyboard
                ? String(root.selectedKeyboard.mappingDetail || "Direct XKB device")
                  + "  ·  " + String(root.selectedKeyboard.name || "")
                : "Omakeyd changes one selected device at a time."
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.caption
              elide: Text.ElideRight
            }

            Text {
              visible: root.selectedKeyboard
                && String(root.selectedKeyboard.rawKeymap || "") !== String(root.selectedKeyboard.effectiveName || "")
              width: parent.width
              text: root.selectedKeyboard
                ? "Effective: " + String(root.selectedKeyboard.effectiveName || "")
                  + "  ·  XKB reports: " + String(root.selectedKeyboard.rawKeymap || "")
                : ""
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }
          }

          PanelSeparator { foreground: root.contentForeground }

          Column {
            width: parent.width
            spacing: Style.space(6)

            PanelSectionHeader {
              text: "SAVED LAYOUTS"
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
            }

            Text {
              visible: root.favorites.length === 0
              text: "Search below to save the first layout."
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.body
            }

            Repeater {
              model: root.favorites

              delegate: Column {
                id: favoriteRow
                required property var modelData
                width: contentColumn.width
                spacing: 0

                Rectangle {
                  width: parent.width
                  height: Style.space(48)
                  radius: Style.cornerRadius
                  color: root.layoutIsActive(favoriteRow.modelData)
                    ? Style.selectedFillFor(root.contentForeground, Color.accent)
                    : "transparent"

                  RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Style.space(9)
                    anchors.rightMargin: Style.space(5)
                    spacing: Style.space(8)

                    Text {
                      text: String(favoriteRow.modelData.brief || "KB")
                      color: root.layoutIsActive(favoriteRow.modelData) ? Color.accent : root.contentDim
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
                        text: String(favoriteRow.modelData.name || "Unnamed layout")
                        color: root.contentForeground
                        font.family: root.contentFontFamily
                        font.pixelSize: Style.font.body
                        font.bold: root.layoutIsActive(favoriteRow.modelData)
                        elide: Text.ElideRight
                      }

                      Text {
                        width: parent.width
                        text: String(favoriteRow.modelData.layout || "")
                          + (favoriteRow.modelData.variant ? " (" + String(favoriteRow.modelData.variant) + ")" : "")
                        color: root.contentDim
                        font.family: root.contentFontFamily
                        font.pixelSize: Style.font.caption
                        elide: Text.ElideRight
                      }
                    }

                    Button {
                      text: root.layoutIsActive(favoriteRow.modelData) ? "ACTIVE" : "APPLY"
                      selected: root.layoutIsActive(favoriteRow.modelData)
                      enabled: !root.busy && root.selectedKeyboard && root.selectedKeyboard.canApply
                        && !root.layoutIsActive(favoriteRow.modelData)
                      fontSize: Style.font.caption
                      horizontalPadding: Style.space(8)
                      verticalPadding: Style.space(5)
                      tooltipText: root.selectedKeyboard
                        ? "Apply to " + String(root.selectedKeyboard.label || root.selectedKeyboard.name)
                        : "Choose a keyboard"
                      onClicked: root.applyLayout(favoriteRow.modelData)
                    }

                    Button {
                      visible: String(favoriteRow.modelData.id || "") !== "qwerty-us"
                      iconText: "\uf1f8"
                      tooltipText: "Remove from saved layouts"
                      enabled: !root.busy
                      horizontalPadding: Style.space(7)
                      verticalPadding: Style.space(5)
                      onClicked: root.removeLayout(favoriteRow.modelData)
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
          }

          PanelSeparator { foreground: root.contentForeground }

          Column {
            width: parent.width
            spacing: Style.space(8)

            PanelSectionHeader {
              text: "FIND A LAYOUT"
              foreground: root.contentForeground
              fontFamily: root.contentFontFamily
            }

            TextField {
              id: layoutSearch
              width: parent.width
              placeholderText: "Search languages, QWERTY, Colemak, Dvorak..."
              foreground: root.contentForeground
              onTextChanged: {
                root.searchQuery = text
                searchDebounce.restart()
              }
            }

            Text {
              visible: root.searchResults.length === 0 && root.searchQuery !== ""
              text: "No installed XKB layouts match."
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.body
            }

            Repeater {
              model: root.searchResults.slice(0, root.searchQuery === "" ? 5 : 10)

              delegate: Item {
                id: searchRow
                required property var modelData
                width: contentColumn.width
                height: Style.space(42)

                RowLayout {
                  anchors.fill: parent
                  spacing: Style.space(8)

                  Column {
                    Layout.fillWidth: true
                    spacing: 0

                    Text {
                      width: parent.width
                      text: String(searchRow.modelData.name || "Unnamed layout")
                      color: root.contentForeground
                      font.family: root.contentFontFamily
                      font.pixelSize: Style.font.body
                      elide: Text.ElideRight
                    }

                    Text {
                      width: parent.width
                      text: String(searchRow.modelData.layout || "")
                        + (searchRow.modelData.variant ? " (" + String(searchRow.modelData.variant) + ")" : "")
                        + "  ·  " + String(searchRow.modelData.source || "system")
                      color: root.contentDim
                      font.family: root.contentFontFamily
                      font.pixelSize: Style.font.caption
                      elide: Text.ElideRight
                    }
                  }

                  Button {
                    text: "SAVE"
                    enabled: !root.busy
                    fontSize: Style.font.caption
                    horizontalPadding: Style.space(8)
                    verticalPadding: Style.space(5)
                    onClicked: root.addLayout(searchRow.modelData)
                  }

                  Button {
                    text: "APPLY"
                    enabled: !root.busy && root.selectedKeyboard && root.selectedKeyboard.canApply
                    fontSize: Style.font.caption
                    horizontalPadding: Style.space(8)
                    verticalPadding: Style.space(5)
                    tooltipText: root.selectedKeyboard
                      ? "Apply once to " + String(root.selectedKeyboard.label || root.selectedKeyboard.name)
                      : "Choose a keyboard"
                    onClicked: root.applyLayout(searchRow.modelData)
                  }
                }
              }
            }
          }

          PanelSeparator { foreground: root.contentForeground }

          Column {
            width: parent.width
            spacing: Style.space(9)

            RowLayout {
              width: parent.width

              PanelSectionHeader {
                text: "CUSTOM LAYOUT"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
                Layout.fillWidth: true
              }

              Button {
                text: root.customExpanded ? "CLOSE" : "BUILD"
                selected: root.customExpanded
                fontSize: Style.font.caption
                horizontalPadding: Style.space(8)
                verticalPadding: Style.space(5)
                onClicked: {
                  root.customExpanded = !root.customExpanded
                  if (root.customExpanded) Qt.callLater(function() { customName.forceActiveFocus() })
                }
              }
            }

            Text {
              visible: !root.customExpanded
              width: parent.width
              text: "Start from an installed layout, then describe the three physical key rows."
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.WordWrap
            }

            Column {
              visible: root.customExpanded
              width: parent.width
              spacing: Style.space(8)

              RowLayout {
                width: parent.width
                spacing: Style.space(8)

                TextField {
                  id: customName
                  Layout.fillWidth: true
                  placeholderText: "Layout name"
                  foreground: root.contentForeground
                }

                TextField {
                  id: customBrief
                  Layout.preferredWidth: Style.space(80)
                  placeholderText: "Badge"
                  foreground: root.contentForeground
                }
              }

              RowLayout {
                width: parent.width
                spacing: Style.space(8)

                TextField {
                  id: customBaseLayout
                  Layout.fillWidth: true
                  text: "us"
                  placeholderText: "Base layout"
                  foreground: root.contentForeground
                }

                TextField {
                  id: customBaseVariant
                  Layout.fillWidth: true
                  placeholderText: "Base variant (optional)"
                  foreground: root.contentForeground
                }
              }

              Text {
                text: "10 space-separated XKB symbols per physical row. Use _ to inherit the base."
                color: root.contentDim
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.caption
              }

              TextField {
                id: customTop
                width: parent.width
                text: "q w f p b j l u y semicolon"
                placeholderText: "Top row"
                foreground: root.contentForeground
              }

              TextField {
                id: customHome
                width: parent.width
                text: "a r s t g m n e i o"
                placeholderText: "Home row"
                foreground: root.contentForeground
              }

              TextField {
                id: customBottom
                width: parent.width
                text: "z x c d v k h comma period slash"
                placeholderText: "Bottom row"
                foreground: root.contentForeground
              }

              Row {
                spacing: Style.space(8)

                Button {
                  text: root.busy && root.pendingAction === "custom" ? "VALIDATING..." : "SAVE LAYOUT"
                  selected: true
                  enabled: !root.busy
                  fontSize: Style.font.caption
                  horizontalPadding: Style.space(10)
                  verticalPadding: Style.space(6)
                  onClicked: root.saveCustom()
                }
              }
            }
          }

          PanelSeparator { foreground: root.contentForeground }

          Column {
            width: parent.width
            spacing: Style.space(9)

            RowLayout {
              width: parent.width

              PanelSectionHeader {
                text: "PHYSICAL REMAP"
                foreground: root.contentForeground
                fontFamily: root.contentFontFamily
                Layout.fillWidth: true
              }

              Button {
                text: root.sourceExpanded ? "CLOSE" : "CONFIGURE"
                selected: root.sourceExpanded
                enabled: !!root.selectedKeyboard
                fontSize: Style.font.caption
                horizontalPadding: Style.space(8)
                verticalPadding: Style.space(5)
                onClicked: {
                  if (root.sourceExpanded) root.sourceExpanded = false
                  else root.openSourceEditor()
                }
              }
            }

            Text {
              visible: !root.sourceExpanded
              width: parent.width
              text: root.selectedKeyboard && root.selectedKeyboard.source
                && Object.keys(root.selectedKeyboard.source).length > 0
                ? "Detected " + String(root.selectedKeyboard.source.name || "a source remap")
                  + ". Omakeyd compensates for it without changing firmware or keyd."
                : "Only needed when firmware or another remapper changes the physical key positions before XKB."
              color: root.contentDim
              font.family: root.contentFontFamily
              font.pixelSize: Style.font.body
              wrapMode: Text.WordWrap
            }

            Column {
              visible: root.sourceExpanded
              width: parent.width
              spacing: Style.space(8)

              TextField {
                id: sourceName
                width: parent.width
                placeholderText: "Source mapping name"
                foreground: root.contentForeground
              }

              Text {
                width: parent.width
                text: "Type what each physical QWERTY position emits now. This is the pre-XKB map, not the layout you want."
                color: root.contentDim
                font.family: root.contentFontFamily
                font.pixelSize: Style.font.caption
                wrapMode: Text.WordWrap
              }

              TextField {
                id: sourceTop
                width: parent.width
                placeholderText: "Source top row"
                foreground: root.contentForeground
              }

              TextField {
                id: sourceHome
                width: parent.width
                placeholderText: "Source home row"
                foreground: root.contentForeground
              }

              TextField {
                id: sourceBottom
                width: parent.width
                placeholderText: "Source bottom row"
                foreground: root.contentForeground
              }

              Button {
                text: root.busy && root.pendingAction === "source" ? "CHECKING..." : "SAVE SOURCE MAP"
                selected: true
                enabled: !root.busy
                fontSize: Style.font.caption
                horizontalPadding: Style.space(10)
                verticalPadding: Style.space(6)
                onClicked: root.saveSource()
              }
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
            text: root.busy ? "Applying one device-specific change..." : "Reading keyboards..."
            color: root.contentDim
            font.family: root.contentFontFamily
            font.pixelSize: Style.font.caption
          }
        }
      }
    }
  }
}
