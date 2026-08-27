# Product

## Register

product

## Users

Omarchy users who type with a positional English layout such as Colemak-DH,
Dvorak, or a personal derivative and occasionally need the physical QWERTY
arrangement again. The common transition is immediate and practical: entering a
game, lending the computer to someone, troubleshooting, or returning to the
everyday layout afterward.

The primary user already relies on keyd for a built-in or otherwise
non-programmable keyboard. Firmware-managed boards and keyboards not managed by
keyd are secondary cases, not concepts the home panel must expose.

## Product Purpose

Omakeyd is a native Omarchy Quattro switcher and visual editor for keyd letter
layouts. It keeps one keyboard's identity mapping (QWERTY) and the user's saved
positional layouts one click away while leaving XKB on the ordinary US layout.

Success means a user can move between Colemak-DH and physical QWERTY in seconds,
see the result in the shell bar, and return after a reboot without editing keyd
configuration or authenticating on every switch.

Omakeyd performs one authenticated setup per keyd profile. That setup creates a
root-owned, Omakeyd-managed keyd layout and installs a narrowly constrained
runtime helper. The helper may only replace the thirty primary-key bindings with
a validated permutation; it cannot execute commands or rewrite arbitrary system
configuration.

## Brand Personality

Precise, calm, and candid. Omakeyd should feel like a small native instrument:
quick enough for a habitual switch, explicit about the keyboard being changed,
and quiet about implementation details that do not require attention.

## Anti-references

- A language catalogue presented as the product's home screen.
- A settings dashboard made from nested cards.
- Raw keyd, evdev, or XKB diagnostics in the everyday switching flow.
- Granting the desktop session unrestricted access to keyd's privileged socket.
- Requiring a password for every layout switch.
- Decorative gamer styling, neon accents, glassmorphism, or animated keyboard
  theatrics.

## Design Principles

1. **Switch first.** The current keyd profile and saved layouts occupy the first
   and only primary view.
2. **QWERTY is the safe identity.** Physical QWERTY is always available and can
   never be deleted.
3. **Name the target before the action.** The profile label sits directly above
   every layout choice.
4. **Keep engines out of the task.** keyd setup and diagnostics are secondary;
   XKB compensation does not appear in the keyd-managed path.
5. **Make custom layouts spatial.** Editing happens on a visual keyboard, not in
   rows of key names or XKB symbols.
6. **Constrain privilege.** Setup is explicit and authenticated; routine
   switching accepts only a complete permutation of the thirty primary keys.
7. **Fail closed.** An invalid mapping, missing managed layer, unavailable keyd
   daemon, or uncertain profile produces an explanation and no persisted state.

## Accessibility & Inclusion

The panel and editor must be fully keyboard-operable, retain visible focus,
expose text in addition to color for every state, honor the live Omarchy theme,
and avoid decorative motion. Key labels use familiar printable characters;
exact keyd identifiers remain available only in diagnostics.
