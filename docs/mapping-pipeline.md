# Mapping model

Omakeyd treats a layout as a forward mapping from the 30 physical QWERTY
positions to the 30 emitted key names:

```text
physical position P → active keyd layout(P) → emitted key
```

For physical QWERTY, the mapping is the identity:

```text
physical E → keyd emits E
```

For the known Colemak-DH map:

```text
physical E → keyd emits F
physical R → keyd emits P
physical M → keyd emits H
```

XKB remains `us` in both cases. There is no inverse compensation layer and no
per-device Hyprland keymap mutation.

## Layout invariant

Every supported layout is a permutation of exactly these keys:

```text
q w e r t y u i o p
a s d f g h j k l ;
z x c v b n m , . /
```

No key may be absent, repeated, or outside that set. This narrow model has three
useful consequences:

- QWERTY can always be reconstructed as a safe identity layout.
- Assigning an already-used key in the visual editor can swap the two positions,
  keeping every draft valid.
- The privileged helper cannot express a macro, command, modifier action, or
  arbitrary keyd binding.

Modifiers, function keys, navigation layers, Compose behavior, and other keyd
bindings remain in the user's existing profile and outside the managed block.
