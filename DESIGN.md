---
name: Omakeyd
description: A precise native Quattro switchboard for per-keyboard layouts.
---

# Design System: Omakeyd

## Overview

**Creative North Star: "The Labeled Switchboard"**

Omakeyd is used in a compact bar panel at the instant someone changes input behavior. It inherits every color, spacing, type, border, and corner decision from Omarchy Quattro through `qs.Commons` and `qs.Ui`; it must look native in every installed theme rather than carrying a private light or dark palette.

The panel is dense but never cryptic. One hero describes the selected keyboard and effective layout. The target selector precedes every layout action. Saved choices scan quickly; search and custom construction unfold beneath them only when needed.

**Key Characteristics:**

- Theme-native, compact, and textually explicit.
- One continuous panel hierarchy, not a dashboard of cards.
- State motion only, 120–180 ms, with no entrance choreography.
- Device identity and mapping provenance are visible before commitment.

## Colors

All colors come from Quattro's live `Color` singleton. `Color.foreground`, `Color.background`, `Color.accent`, semantic urgent/error colors, and alpha-derived dividers are the only palette. Omakeyd owns no hex values.

**The Borrowed Palette Rule.** A plugin that looks correct in only one Omarchy theme is incorrect.

**The One Signal Rule.** Accent color identifies the current selection, focus, and the primary apply action. It is never decoration.

## Typography

Every label uses `Style.font.family`. The hero uses `Style.font.title`; row labels use `Style.font.body`; metadata and physical identifiers use `Style.font.caption`. Bold weight distinguishes current state and section labels. Device and XKB identifiers elide on one line and remain available in a tooltip or detail line.

**The Two Names Rule.** Prefer the human label first, then the exact system identifier in quieter text.

## Elevation

Omakeyd is flat by default. Depth comes from Quattro's panel surface, control borders, popup surfaces, and tonal hover/focus fills. It introduces no private shadows or blur.

**The Single Surface Rule.** Do not nest card surfaces inside the panel. Separators, spacing, and headers establish hierarchy.

## Components

### Bar indicator

A compact effective-layout brief, always visible when a usable keyboard exists. Its tooltip names the keyboard, effective layout, and raw XKB layout when those differ. Left click opens the panel; wheel may move between saved layouts only when the target is unambiguous.

### Target selector

A searchable Quattro dropdown placed before layout actions. Each option combines a human device label with its effective layout. Virtual, remapped, disconnected, and ambiguous devices carry text badges rather than color-only states.

### Saved layout row

A full-width row with layout name, brief, source, and a trailing apply action. The selected row uses Quattro's selected fill and border vocabulary. Its action copy names the target when space allows; the panel header always supplies the same context.

### Layout search

Quattro's searchable dropdown over installed XKB layouts and variants. Results show description first and `layout (variant)` second. Selecting a result stages it; a separate explicit action saves or applies it.

### Custom layout editor

An inline secondary section with name, base layout, and three physical key-row fields. It previews the resulting rows and reports validation errors beside the editor. It never appears as a modal.

### Status and errors

Short inline messages sit next to the action that caused them. Errors say what was unchanged. Mapping ambiguity blocks Apply and explains how the user can select or configure a source map.

## Do's and Don'ts

### Do:

- **Do** state the selected keyboard immediately above all layout actions.
- **Do** distinguish effective physical layout from raw XKB keymap whenever keyd or firmware remapping is present.
- **Do** reuse Quattro controls and dynamic theme tokens without private approximations.
- **Do** keep QWERTY and the user's current everyday layout one action away after first use.
- **Do** preserve Compose and unrelated input options by changing only per-device layout and variant values.

### Don't:

- **Don't** build a global language flag that hides the target keyboard.
- **Don't** build a settings dashboard made from nested cards.
- **Don't** report raw XKB names as if they were always the effective physical layout.
- **Don't** rewrite `/etc/keyd` or ask for a password on every switch.
- **Don't** use decorative gamer styling, neon accents, glassmorphism, or animated keyboard theatrics.
- **Don't** use side-stripe borders, gradient text, or a modal as the first custom-layout affordance.
