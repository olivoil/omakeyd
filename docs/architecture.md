# Architecture

Omakeyd consists of a Quattro bar widget, a popup panel, a small restore service, and a Python standard-library backend.

```text
Omakeyd.qml ─┬─ snapshot / quick cycle ─┐
             └─ loads Panel.qml         │
                                        ├─ bin/omakeyd → omakeyd/core.py
Service.qml ─── explicit restore ───────┘                 │
                                                          ├─ hyprctl
                                                          ├─ xkbcli
                                                          ├─ ~/.config/omakeyd/config.json
                                                          └─ ~/.config/xkb/symbols/
```

## State boundaries

- Hyprland owns connected-device and active-keymap truth. Omakeyd reads `hyprctl -j devices` after actions and compositor events.
- XKB owns the installed layout catalogue and compilation rules. Omakeyd treats `xkbcli compile-keymap` as the validator.
- keyd and firmware are pre-XKB sources. Omakeyd reads simple keyd letter mappings but never modifies them.
- Omakeyd owns only saved user intent: target layout, selected device, aliases, custom rows, and manual source maps.

## Device selection

The backend excludes button endpoints, consumer/system controls, fcitx-style virtual injection devices, and an underlying AT keyboard grabbed by a detected keyd virtual path. Unknown hardware stays visible; false inclusion is easier to correct than silently hiding a real keyboard.

Every mutation receives one exact Hyprland device name. The backend has no `all` mode.

## Apply transaction

1. Confirm that the named device remains connected.
2. Compile the requested layout and variant with XKB.
3. Resolve any pre-XKB source map.
4. For a direct device, use the requested XKB layout unchanged.
5. For a remapped device, generate and compile a deterministic compensation layout.
6. Set only that device's `kb_variant` and `kb_layout` through `hyprctl keyword device[name]:…`.
7. Persist the requested physical layout and the runtime layout only after Hyprland accepts the change.

The service restores only entries created by step 7. A first installation never changes an active keyboard.

## Mutable files

Configuration and XKB files use a write-to-temporary + `fsync` + atomic replace sequence. Custom files are rolled back if XKB compilation fails. Omakeyd refuses to overwrite a same-named XKB file that lacks its generated-file marker.
