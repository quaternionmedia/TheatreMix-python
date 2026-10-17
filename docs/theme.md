# TheatreMix grid colours (`theme.py`)

The `/theatremix` DCA grid uses one colour table, in `src/theatremix/theme.py`.

## What each colour means

Each DCA cell is coloured by what that DCA does in the **next** cue. The colour is the
cell background. A DCA counts as on when its cell has channels.

| State | Meaning | Key and default |
|---|---|---|
| green | the same channels stay assigned in the next cue | `stays_on` = `green-8` |
| grey | the DCA is on now and muted (no channels) in the next cue | `muted_next` = `grey-7` |
| orange | the DCA is on now and gets different channels in the next cue | `changed` = `orange-8` |
| none | the cell is empty and stays empty, or it is the last cue | no tint |

Row tint comes from `Cue.colour`, an index into `ROW_COLOURS` (0 = no tint). A row tint
shows in cells that have no state of their own. The TheatreMix app's own palette is not
documented, so `ROW_COLOURS` is a starting point.

Script viewer chips use the same background colours.

## Accepted values

Colours are Quasar palette names such as `green-8`, `red-10` or `grey-7`. The grid
uses them as background classes (`bg-<name>`).
See https://quasar.dev/style/color-palette.

## Changing them

Option 1: edit `COLORS` or `ROW_COLOURS` in `src/theatremix/theme.py`, then reload the page.

Option 2: override the cell states per show in `show.toml`:

```toml
[plugins.theatremix.colors]
stays_on = "teal-8"
muted_next = "blue-grey-7"
changed = "amber-8"
```

Unknown keys are ignored (`stays_on`, `muted_next` and `changed` are the only keys). Overrides apply at startup, so restart ShowRunner after changing `show.toml`.
