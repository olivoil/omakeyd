# Mapping model

Omakeyd treats a layout as a forward mapping from 30 physical QWERTY positions
to XKB symbols:

```text
physical position P → per-device XKB layout(P) → emitted symbol
```

For QWERTY, the mapping is the identity. For the included Colemak-DH layout:

```text
physical E → F
physical R → P
physical M → H
physical Z → Z
```

The ISO `<LSGT>` key is not changed. This avoids the angle modification that
moves Z to the physical `< >` key on some Colemak-DH variants.

## Layout invariant

Every layout is a permutation of exactly these keys:

```text
q w e r t y u i o p
a s d f g h j k l ;
z x c v b n m , . /
```

No key may be absent, repeated, or outside that set. Generated files therefore
contain only static two-level letter and punctuation symbols. Modifiers,
function keys, navigation, Compose, and shortcuts continue to come from the
user's normal Hyprland/XKB configuration.
