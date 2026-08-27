# Architecture

Omakeyd has a theme-native Quattro surface, an unprivileged Python backend, and
two deliberately separate privileged programs.

```text
Omakeyd.qml ─┬─ snapshot / quick switch ─┐
             └─ loads Panel.qml          ├─ bin/omakeyd → omakeyd/core.py
Service.qml ─── persistent-state status ─┘                    │
                                                              ├─ reads /etc/keyd/*.conf
                                                              ├─ ~/.config/omakeyd/config.json
                                                              └─ pkexec
                                                                  │
                          one-time ── helper/omakeyd-setup ────────┤
                          routine  ── installed omakeyd-helper ────┘
                                                                  │
                                                                  ├─ keyd check
                                                                  ├─ atomic profile replace
                                                                  └─ restart keyd and verify
```

## State boundaries

- keyd owns the effective physical letter layout and persistent runtime truth.
- XKB stays on US and is outside Omakeyd's mutation boundary.
- Omakeyd's user configuration owns the selected profile, last requested layout,
  and custom visual-layout definitions.
- A keyd profile identifies the physical devices it owns through its `[ids]`
  section. Omakeyd does not infer keyboards from Hyprland's broad input-device
  list.
- The installed helper owns no policy decisions. It accepts only already-valid
  managed profiles and complete primary-key permutations.

## Discovery

The backend reads regular `*.conf` files under `/etc/keyd` and keeps those with
an `[ids]` section. It composes simple primary-key bindings from `[main]` and the
configured default layout to describe the current effective rows.

An exact match for the known Colemak-DH rows is named **Colemak-DH**. Other valid
one-to-one primary maps are presented as detected layouts. QWERTY is synthesized
as the identity map, independent of system catalogues.

A profile is ready only when all three facts agree:

1. The expected Omakeyd begin and end markers occur exactly once.
2. The marked block contains `[omakeyd_<profile>:layout]`.
3. `[global] default_layout` points at that layer.

## Authenticated setup transaction

The setup program is run from the plugin directory through the system's normal
`pkexec` authentication. It accepts only a profile stem and resolves the path
under `/etc/keyd`.

1. Require a root-owned, non-symlink, non-group/world-writable profile.
2. Reject existing Omakeyd markers, `setlayout()` use, a non-main default layout,
   or a non-permutation primary map.
3. Compose the current `[main]` letter map and generate a full managed layout.
4. Point `default_layout` at the managed layout in staged content.
5. Validate the staging file with `keyd check`.
6. Install the runtime helper and its PolicyKit action as root-owned files.
7. Create a timestamped backup, atomically replace the profile, and restart
   `keyd`.
8. Check that the service stays healthy; restore the original content and
   restart again if activation fails.

The existing `[main]` bindings are preserved. The managed layout overrides all
30 supported positions, so its initial behavior is identical to the pre-setup
mapping.

## Routine apply transaction

The unprivileged backend validates and resolves a saved layout, then calls the
fixed installed helper through `pkexec`. PolicyKit permits active local sessions
to run that exact helper without repeated authentication.

The helper independently validates every input and then:

1. Take a root-owned runtime lock so concurrent switches cannot interleave.
2. Resolve `/etc/keyd/<profile>.conf`; reject symlinks and unsafe ownership or
   modes.
3. Require the expected default layout and exact managed markers.
4. Require all 30 allowed key names exactly once; actions and arbitrary targets
   cannot pass this grammar.
5. Replace only the marked block in memory.
6. Write and `fsync` a staging file beside the profile.
7. Run `keyd check` on the staging file.
8. Atomically replace the profile and `fsync` its directory.
9. Restart `keyd`, check that it stays healthy, and restore the previous content
   if activation fails.

Only after the helper succeeds does the unprivileged backend record the last
requested layout. Snapshot state is still derived from the actual keyd profile,
not that advisory value. If the service is down, the profile is reported as
configured state and no layout is presented as currently active.

## Why not the keyd socket

keyd documents socket access as privileged because dynamic bindings can include
commands and arbitrary actions. Omakeyd therefore neither changes socket group
membership nor proxies generic `keyd bind` expressions. The much smaller helper
grammar is the security boundary.
