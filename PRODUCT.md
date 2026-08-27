# Product definition

Omakeyd is an Omarchy bar plugin for people who regularly switch between
QWERTY, Colemak-DH, or another custom letter layout.

The built-in Omarchy keyboard widget can cycle XKB groups. Omakeyd adds a panel
that names those layouts, switches directly to one, handles multiple physical
keyboards, and provides a small visual editor.

## Principles

1. Put switching first.
2. Show the physical keyboard selector only when it is useful.
3. Keep QWERTY and Colemak-DH built in.
4. Store settings and generated XKB symbols in the user's configuration.
5. Use Hyprland's supported per-device API and verify every switch.
6. Do not request authentication or install system components.
7. Treat keyd as a visible conflict instead of trying to manage it.

## Scope

Omakeyd rearranges the 30 keys shown in its editor. It does not manage macros,
modifiers, shortcuts, Compose, navigation layers, firmware, or system services.
