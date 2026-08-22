# Product

## Register

product

## Users

Omarchy users who type with Colemak-DH, Dvorak, language-specific XKB layouts, firmware-remapped keyboards, keyd, or a mixture of those. They open Omakeyd at a transition point, often just before a game or when moving between a laptop keyboard and an external board. They need to know which physical input path will change before they commit.

## Product Purpose

Omakeyd is a native Omarchy Quattro keyboard-layout switcher. It discovers real typing keyboards, explains remapping layers such as keyd, lets people search the installed XKB catalogue, save useful layouts, create a layout from physical key rows, and apply a layout to one explicit keyboard.

Success means a user can move between their everyday layout and QWERTY in seconds without changing another keyboard, losing their Compose options, editing system files, or guessing whether a firmware or keyd remap sits underneath XKB.

## Brand Personality

Precise, calm, and candid. Omakeyd should feel like a small native instrument: quick enough for a habitual switch, explicit enough for a risky one, and honest about what the system can and cannot observe.

## Anti-references

- A global language flag that hides the target keyboard.
- A settings dashboard made from nested cards.
- A layout picker that reports raw XKB names as if they were always the effective physical layout.
- A privileged helper that rewrites `/etc/keyd` or asks for a password on every switch.
- Decorative gamer styling, neon accents, glassmorphism, or animated keyboard theatrics.

## Design Principles

1. **Name the target before the action.** Every apply control names the keyboard it will affect.
2. **Describe the whole mapping path.** Show physical source remaps, generated compensation, and active XKB separately when they differ.
3. **Make the common reversal immediate.** Saved layouts such as Colemak-DH and QWERTY stay one click away.
4. **Reveal complexity progressively.** Search and switching are primary; custom key rows and mapping diagnostics are available without crowding the default panel.
5. **Fail closed.** An ambiguous virtual keyboard, invalid custom symbols, or disconnected target produces an explanation and no layout change.

## Accessibility & Inclusion

The panel must be fully keyboard-operable, retain visible focus, expose text in addition to color for every state, honor the live Omarchy theme, and avoid decorative motion. Labels must remain understandable for users who do not know XKB terminology; exact identifiers remain available as supporting detail.
