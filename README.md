# Omakeyd

Omakeyd is an Omarchy bar plugin for switching letter layouts on keyboards
managed by [keyd](https://github.com/rvaiya/keyd).

keyd is a Linux service that remaps keys before they reach desktop applications.
It is commonly used for layouts such as Colemak on built-in keyboards. Omakeyd
adds a small interface for switching those mappings without editing keyd
configuration by hand.

![Omakeyd showing QWERTY and Colemak-DH](preview.png)

## What it does

- Keeps QWERTY and your saved layouts one click away.
- Detects the letter mapping already present in a keyd profile.
- Switches one selected keyd profile at a time.
- Provides a visual three-row editor for custom layouts.
- Shows a profile selector when more than one keyd profile is available.
- Leaves Omarchy's normal US keyboard setting unchanged; keyd performs the
  remapping underneath.

Omakeyd changes only the 30 letter and punctuation positions shown in its
editor. It does not create keyd macros, shortcuts, or arbitrary commands.

## Requirements

- Omarchy Quattro
- Python 3
- keyd installed and running
- A keyd device profile under `/etc/keyd/` with an `[ids]` section
- PolicyKit and `pkexec` for the one-time setup

Omakeyd is intended for keyboards managed by keyd. Keyboards remapped only in
firmware, or keyboards without a keyd profile, do not appear in the profile
selector.

## Install

Install and enable Omakeyd with the standard Omarchy plugin command:

```bash
omarchy plugin add https://github.com/olivoil/omakeyd.git --enable
```

If Omarchy's first-party keyboard-layout badge is also enabled:

```bash
omarchy plugin disable omarchy.keyboard-layout
```

## First setup

Omakeyd must prepare each keyd profile once before it can switch that profile.

1. Open Omakeyd and select the profile.
2. Choose **Review setup**.
3. Review the exact keyd file that will change.
4. Choose **Authenticate & set up** and approve the PolicyKit prompt.

Setup then:

- Creates a timestamped backup beside the original keyd profile.
- Preserves the current 30-key mapping as an Omakeyd layout.
- Adds one clearly marked Omakeyd-managed layout block.
- Validates the staged profile with `keyd check`.
- Restarts keyd, checks that it stays healthy, and restores the original file
  if activation fails.
- Installs a small restricted helper and PolicyKit action for later switches.

Routine layout switches do not require another password. The helper accepts only
a keyd profile identifier and a complete permutation of the 30 supported keys.

Automatic setup supports simple profiles whose letter mappings are in
`[main]`. Omakeyd refuses profiles that already use `setlayout()` or a
non-main default layout because changing them automatically would be ambiguous.

## Use

- Click the keyboard indicator in the bar to open Omakeyd.
- If several keyd profiles exist, select the keyboard profile first.
- Choose **Switch** beside a saved layout.
- Choose **New layout** to create a layout in the visual editor.
- Use the info button for profile, helper, and configuration details.
- Scroll or right-click the bar indicator to cycle layouts for the selected
  ready profile.

If keyd stops, Omakeyd shows that no layout is active and offers to restart it.
When Omarchy has recorded a keyd crash, Omakeyd can also hand it to the default
Omarchy agent through the standard **Diagnose with AI** flow.

QWERTY is always available and cannot be deleted.

## System access

Before setup, Omakeyd reads keyd profiles under `/etc/keyd/` but does not
modify them. It stores user settings in:

```text
~/.config/omakeyd/config.json
```

During the explicit authenticated setup, Omakeyd modifies only the selected
keyd profile and installs:

```text
/usr/local/libexec/omakeyd-helper
/usr/share/polkit-1/actions/io.github.olivoil.omakeyd.policy
```

It does not make network requests, add the user to keyd's privileged group, or
modify Hyprland and desktop keyboard configuration.

## Remove

Remove the plugin checkout with the standard Omarchy command:

```bash
omarchy plugin remove io.github.olivoil.omakeyd
```

Removing the checkout does not undo the one-time keyd setup. This preserves the
active keyboard mapping and its backup instead of changing input behavior during
uninstallation.

To restore the original keyd profile, use the exact backup path reported during
setup:

```bash
sudo install -o root -g root -m 0644 \
  /etc/keyd/PROFILE.conf.omakeyd-backup-TIMESTAMP \
  /etc/keyd/PROFILE.conf
sudo keyd check /etc/keyd/PROFILE.conf
sudo systemctl restart keyd.service
```

After restoring the profile, the installed runtime files can be removed
separately:

```bash
sudo rm -f /usr/local/libexec/omakeyd-helper
sudo rm -f /usr/share/polkit-1/actions/io.github.olivoil.omakeyd.policy
```

Replace the placeholders with the profile and backup names shown by Omakeyd.

## Command line

The backend prints JSON:

```bash
bin/omakeyd snapshot
bin/omakeyd apply --profile laptop-colemak-dh --layout-id qwerty
bin/omakeyd apply --profile laptop-colemak-dh --layout-id colemak-dh-yoga
bin/omakeyd doctor
```

## Development

Run the complete local check:

```bash
scripts/ci.sh
```

The suite covers profile discovery, configuration migration, layout validation,
helper isolation, failure rollback, the plugin contract, and panel linting.

See [architecture](docs/architecture.md) and
[mapping model](docs/mapping-pipeline.md) for implementation details.
