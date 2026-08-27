# Architecture

Omakeyd has a Quattro panel, a small Python backend, and no privileged
component.

```text
Omakeyd.qml ─┬─ snapshot / quick switch ─┐
             └─ loads Panel.qml          ├─ bin/omakeyd → omakeyd/core.py
Service.qml ─── restore saved layouts ───┘                    │
                                                              ├─ hyprctl devices
                                                              ├─ hyprctl eval hl.device(...)
                                                              ├─ hyprctl switchxkblayout
                                                              ├─ ~/.config/omakeyd/config.json
                                                              └─ ~/.config/xkb/symbols/omakeyd_*
```

## State boundaries

- Hyprland reports connected keyboards and the active XKB layout index.
- Omakeyd stores only the selected keyboard, last layout per keyboard, and
  custom 30-key layouts.
- Generated XKB symbols are user-owned and contain only static key symbols.
- The service entry point reapplies saved per-device layouts after the shell
  starts because dynamic Hyprland device settings reset on a config reload.
- When the service is unloaded, it restores the per-device settings captured
  before Omakeyd's first successful switch.
- keyd is treated as a conflict. Omakeyd never stops it or changes its files.

## Apply transaction

1. Refuse to apply while keyd is active.
2. Confirm that the selected physical keyboard is connected.
3. Validate every layout as a complete permutation of the 30 supported keys.
4. Generate and compile user-owned XKB symbol files.
5. Configure the layout list for that device with Hyprland's `hl.device()` API.
6. Select the requested index with `hyprctl switchxkblayout`.
7. Read the device state back and verify the active index.
8. Save the requested layout only after verification succeeds.

If configuration or switching fails, Omakeyd reapplies the device's previous
layout list and index. Every external command is executed directly as an
argument vector; no shell, `sudo`, `pkexec`, PolicyKit action, or system helper
is involved.

## Keyboard discovery

Hyprland reports power buttons, virtual input-method devices, and other
non-typing inputs in its keyboard list. Omakeyd filters known auxiliary and
virtual devices. Remaining physical keyboards become selectable profiles in the
panel, and each can keep a different last layout.
