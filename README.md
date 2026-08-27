# Omakeyd

Omakeyd is a native Omarchy Quattro panel for switching the **effective physical layout of one explicit keyboard**.

It searches the layouts already installed through XKB, keeps everyday layouts one click away, builds custom layouts from physical key rows, and accounts for remappers such as keyd or keyboard firmware before it applies anything.

## Why it exists

Hyprland's built-in keyboard-layout widget cycles a preconfigured XKB list. That is useful for a simple keyboard, but it cannot explain a pipeline such as:

```text
Yoga keyboard → keyd Colemak-DH remap → keyd virtual keyboard → XKB "us"
```

In that pipeline, XKB truthfully reports `English (US)` while the keys are effectively Colemak-DH. Applying `us` again cannot produce physical QWERTY.

Omakeyd separates the requested physical layout from the runtime XKB layout. For QWERTY on that Yoga path it generates a user-owned compensation layout, applies it only to `keyd-virtual-keyboard`, and leaves `/etc/keyd` untouched.

## What the panel does

- Shows the selected keyboard before every action, with the exact Hyprland identifier underneath.
- Shows effective layout, raw XKB keymap, and remapping path when they differ.
- Saves layouts for one-click switching; right click or scroll on the bar badge cycles them.
- Searches the complete `xkbcli list --load-exotic` catalogue by language, description, layout, or variant.
- Discovers layouts under `~/.config/xkb/symbols`, including `colemak_dh_yoga`.
- Builds a custom XKB layout from three ten-key physical rows and validates it before saving.
- Lets firmware-remapped keyboards declare their pre-XKB physical rows.
- Restores only choices explicitly made through Omakeyd after a Hyprland config reload.
- Refuses ambiguous keyd pipelines instead of changing a guessed device.

## How compensation works

For example, Omakeyd can detect a laptop keyboard that keyd remaps before XKB:

| Stage | Device/layout | Meaning |
|---|---|---|
| Physical source | `at-translated-set-2-keyboard` | Grabbed by keyd; not offered as the active target. |
| Pre-XKB remap | `/etc/keyd/laptop-colemak-dh.conf` | Emits the Colemak-DH Yoga letter positions. |
| Hyprland target | `keyd-virtual-keyboard` | The device applications actually type through. |
| Raw XKB | `us` / `English (US)` | Leaves keyd's mapping unchanged, so the effective result is Colemak-DH Yoga. |

The exact primary rows are:

```text
q w f p b j l u y ;
a r s t g m n e i o
z x c d v k h , . /
```

The same XKB definition is retained in [`presets/colemak_dh_yoga`](presets/colemak_dh_yoga). Omakeyd does not overwrite the installed copy.

A separate direct-XKB keyboard remains unchanged unless it is selected explicitly. A keyboard that remaps in firmware can be described in **Physical remap** using the rows it emits; Omakeyd will then compensate layouts for that device too.

## Install

Review the repository, then add the plugin:

```bash
omarchy plugin add https://github.com/olivoil/omakeyd.git
```

Accept the prompt to enable Omakeyd. For an unattended install from a repository you already trust:

```bash
omarchy plugin add https://github.com/olivoil/omakeyd.git --enable --yes
```

Then remove the first-party layout badge if both are on the bar:

```bash
omarchy plugin disable omarchy.keyboard-layout
```

Quattro reloads user plugin code automatically. If needed:

```bash
omarchy-shell shell rescanPlugins
```

## Update

Review and apply the next fast-forward update:

```bash
omarchy plugin update io.github.olivoil.omakeyd
```

Or update all Git-managed plugins:

```bash
omarchy plugin update --all
```

## Use

- Left click the badge to open Omakeyd.
- Select the target keyboard first.
- Use **Apply** on QWERTY, Colemak-DH Yoga, or another saved layout.
- Search by a language or layout name, then **Save** or **Apply**.
- Expand **Custom layout** to build a layout. Each row accepts ten space-separated XKB symbols; `_` inherits the base key and `lower:upper` supplies an explicit shifted pair.
- Expand **Physical remap** only when firmware or another remapper changes positions before XKB.

The backend is also usable directly:

```bash
bin/omakeyd snapshot
bin/omakeyd catalog --query dvorak
bin/omakeyd apply --device logitech-pro-x --layout us --name "QWERTY (US)" --brief US
bin/omakeyd doctor
```

Every command prints JSON. `apply` always requires `--device`; there is no global or `all` target.

## Security and system access

Plugins run unsandboxed inside `omarchy-shell` when enabled. Review the source before installing it.

Omakeyd invokes the local `hyprctl` and `xkbcli` commands to discover keyboards, inspect and validate layouts, and apply per-device XKB settings. It reads installed XKB metadata and simple mappings from `/etc/keyd/*.conf` when keyd is present. It makes no network requests.

Omakeyd uses only user-owned state:

- `~/.config/omakeyd/config.json`: saved layouts, selected target, explicit restore state, aliases, and manual source maps.
- `~/.config/xkb/symbols/omakeyd_*`: validated custom layouts.
- `~/.config/xkb/symbols/omakeyd_comp_*`: deterministic compensation layouts.

It never edits `~/.config/hypr`, `/etc/keyd`, or `/usr/share/omarchy`, and it does not use `sudo` or `pkexec`.

Its small background service runs once when loaded and after Hyprland configuration reloads. It reapplies only per-device layouts previously selected through Omakeyd.

## Limits

- If several keyd configuration files feed one `keyd-virtual-keyboard`, Omakeyd blocks switching until a source map is chosen. It cannot infer which physical board produced a particular key event.
- Firmware remaps are not introspectable through Hyprland. Configure their emitted rows once in **Physical remap**.
- The compensation approach applies to applications receiving keyboard input through Hyprland/XKB. Software that opens a raw evdev device directly can bypass compositor layout handling.

## Development

```bash
scripts/ci.sh
```

To run Omarchy's structural validator directly:

```bash
omarchy plugin validate .
```

The suite validates the plugin manifest and panel QML when Omarchy tooling is present, exercises catalogue and device filtering, and regression-tests the full keyd → XKB compensation path. Quattro's typed IPC entry points are smoke-tested in a running Omarchy shell because the standalone `qmllint 1.0` shipped on current Omarchy rejects that same valid syntax in first-party plugins.

See [`docs/architecture.md`](docs/architecture.md) for the state model and [`docs/mapping-pipeline.md`](docs/mapping-pipeline.md) for the mapping math.
