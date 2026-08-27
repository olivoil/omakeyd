---
name: Omakeyd
description: A precise native Quattro switcher for keyd letter layouts.
---

# Design System: Omakeyd

## Overview

**Creative North Star: "The Keyboard Toggle"**

Omakeyd is opened at the moment someone wants a different physical typing
arrangement. It inherits every color, spacing, type, border, and corner decision
from Omarchy Quattro through `qs.Commons` and `qs.Ui`; it must look native in
every installed theme rather than carrying a private light or dark palette.

The home panel has one job: identify the keyd-managed keyboard and switch among
the user's layouts. Setup, diagnostics, and visual layout authoring live behind
secondary actions. The interface never asks an everyday user to reason about a
virtual keyboard, a source map, or XKB compensation.

**Key Characteristics:**

- Theme-native, compact, and immediately actionable.
- One continuous panel hierarchy, not a dashboard of cards.
- A stable keyboard icon plus a short live layout code in the bar.
- State motion only, 120–180 ms, with no entrance choreography.

## Colors

All colors come from Quattro's live `Color` singleton. `Color.foreground`,
`Color.background`, `Color.accent`, semantic urgent/error colors, and
alpha-derived dividers are the only palette. Omakeyd owns no hex values.

**The Borrowed Palette Rule.** A plugin that looks correct in only one Omarchy
theme is incorrect.

**The One Signal Rule.** Accent identifies the active layout, visible focus, and
the primary setup or save action. It is never decoration.

## Typography

Every label uses `Style.font.family`. The profile name uses `Style.font.title`;
layout rows use `Style.font.body`; supporting status uses `Style.font.caption`.
Bold weight distinguishes the current layout. System identifiers elide on one
line and remain available in diagnostics.

**The Human Name Rule.** Say “Built-in keyboard” and “Colemak-DH Yoga” before
showing `laptop-colemak-dh` or another exact identifier.

## Elevation

Omakeyd is flat by default. Depth comes from Quattro's panel surface, control
borders, popup surfaces, and tonal hover/focus fills. It introduces no private
shadows or blur.

**The Single Surface Rule.** Do not nest card surfaces inside the panel.
Separators, spacing, and headers establish hierarchy.

## Components

### Bar indicator

A keyboard glyph is the stable plugin identity. The active layout brief sits
beside it when room permits, for example `⌨ DH`. Its tooltip names the profile
and current layout. Left click opens the panel; wheel moves between saved
layouts only when one ready profile is selected.

### Profile header

The first panel row names the target profile and current layout. A selector only
appears when several keyd profiles exist. A short “Setup required” status replaces
layout actions until the selected profile has an Omakeyd-managed keyd layer.

### My layout row

The whole row is the apply target. It contains a short code, human name, and a
textual current marker. The current row uses Quattro's selected vocabulary.
QWERTY is fixed; other rows expose edit or remove through a quiet trailing menu.

### Add layout action

One secondary row opens layout creation. The home panel never shows arbitrary
catalogue results. Initial creation starts from QWERTY, an existing saved
layout, or the mapping detected during profile setup.

### Layout Studio

A dedicated secondary surface presents the thirty primary positions as three
visual key rows. Selecting a key opens a searchable assignment control; typing a
printable key assigns it directly. The editor provides undo, redo, reset,
duplicate, validation, and a typing test. Raw keyd syntax is not an input mode.

### Setup and diagnostics

Setup explains the exact root-owned keyd file that will be migrated, the backup
that will be made, and that one authentication is required. Diagnostics show
profile id, managed layer, helper version, keyd service state, and the last
error. None of this appears on the ready home panel.

### Status and errors

Short inline messages sit next to the action that caused them. Errors say that
the previous profile is restored. Busy feedback names the requested layout;
it never uses vague copy such as “Applying one device-specific change.”

## Do's and Don'ts

### Do:

- **Do** keep QWERTY and the everyday layout one click away.
- **Do** show a keyboard icon in the shell bar even when status is unavailable.
- **Do** state the selected keyd profile immediately above layout choices.
- **Do** reuse Quattro controls and dynamic theme tokens.
- **Do** require an explicit authenticated setup before touching root-owned
  keyd configuration.

### Don't:

- **Don't** put a language catalogue on the home panel.
- **Don't** show virtual-keyboard or XKB-pipeline diagnostics by default.
- **Don't** grant the user unrestricted access to the keyd socket.
- **Don't** ask users to type space-separated key names.
- **Don't** build a settings dashboard made from nested cards.
- **Don't** use decorative gamer styling, side-stripe accents, gradient text,
  glassmorphism, or a modal as the first editor affordance.
