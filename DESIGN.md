---
name: Omakeyd
description: A small Omarchy panel for switching keyboard layouts.
---

# Design system

Omakeyd follows the Omarchy Quattro shell. It uses shell typography, spacing,
buttons, dividers, colors, and the standard `KeyboardPanel` popout.

## Panel structure

1. Current layout and keyboard name.
2. Keyboard selector, shown only when several physical keyboards are connected.
3. Saved layouts with a direct **Switch** action.
4. **New layout** and a quiet info icon.

The layout editor uses three rows of ten keycaps. Assigning a key already in use
swaps the two positions, so the layout remains valid.

## States

- The current layout row uses the selected fill and reads **Current**.
- The bar button uses its standard active underline while the panel is open.
- A keyd conflict is shown in the panel and disables switching.
- Backend and validation failures appear as short inline messages.
- Keyboard and XKB paths are available only in the details view.

## Voice

Use short, literal labels: **Keyboard**, **My layouts**, **Switch**, **Current**,
and **New layout**. Avoid claims about performance, intelligence, or automation.
