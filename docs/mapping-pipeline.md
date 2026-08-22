# Mapping pipeline

For a direct keyboard, the desired layout is also the runtime XKB layout:

```text
physical position P → XKB target(P)
```

For a keyd or firmware-remapped keyboard, an earlier stage changes the emitted key position:

```text
physical position P → source(P) = E → XKB runtime(E)
```

Omakeyd wants the final symbol to equal `target(P)`, so it generates the runtime overrides:

```text
runtime(source(P)) = target(P)
```

Example from the Yoga mapping:

```text
physical E → keyd emits F
QWERTY wants physical E → "e"
generated XKB assigns emitted F → "e"
```

This is an inverse-position compensation, not a second forward Colemak mapping.

## Mapping requirements

Source maps must be a one-to-one permutation of the thirty primary key positions. Duplicate emitted positions are rejected because an inverse would be ambiguous. Unlisted keyd positions pass through unchanged.

The generated XKB file includes the target layout first, preserving its punctuation, modifier, and higher-level behavior. It overrides only positions moved by the source map with the target symbols compiled for their original physical positions.

Generated names are content-addressed from the source mapping plus target layout and variant. Reapplying the same combination reuses the same file.
