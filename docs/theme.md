# TheatreMix grid colours (`theme.py`)

The `/theatremix` DCA grid uses one colour table, in `src/theatremix/theme.py`.

## What each colour means

Each DCA cell is compared with the same DCA on the previous cue:

| State | Meaning | Default colour key |
|---|---|---|
| `new` | label or channels set or changed since the previous cue | `new` = `green-4` |
| `same` | unchanged from the previous cue | `same` = `white` |
| `cleared` | this cue clears the DCA (it had a label before) | `cleared` = `red-4` |
| `empty` | no label, nothing before it either | `empty` = `grey-7` |

Row tint comes from `Cue.colour`, an index into `ROW_COLOURS` (0 = no tint). The
TheatreMix app's own palette is not documented, so `ROW_COLOURS` is a starting point.

## Accepted values

Colours are Quasar palette names such as `green-4`, `red-10` or `white`. The grid
uses them as CSS classes (`text-<name>` for cells, `bg-<name>` for row tint).
See https://quasar.dev/style/color-palette.

## Changing them

Option 1: edit `COLORS` or `ROW_COLOURS` in `src/theatremix/theme.py`, then reload the page.

Option 2: override the four cell states per show in `show.toml`:

```toml
[plugins.theatremix.colors]
new = "cyan-4"
cleared = "orange-4"
```

Unknown keys are ignored. Overrides apply at startup, so restart ShowRunner after changing `show.toml`.
