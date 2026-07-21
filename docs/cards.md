# Cards

Lovelace cards for the [Ecowitt Local](https://github.com/) HACS integration
(`ecowitt_local`) â€” one station overview plus focused sub-cards you can lay out
however you like.

No Lit, no CDN, no build step. A single plain-JavaScript file registers every
card.

## Cards

| Card | Shows |
| --- | --- |
| `ecowitt-weather-card` | Station overview: temperature, feels-like, dew point, an inline wind compass, and a row of metric tiles you choose and order yourself |
| `ecowitt-wind-card` | Two columns: a compass with a dashed average-direction marker on the left, and on the right the speed, a Beaufort description, and rows for direction, gust, daily maximum and average direction. The rows flow into two columns on wider cards |

### Which way the wind arrow points

Wind direction is reported as the bearing the wind blows **from** â€” a reading
of 89Â° means an easterly. The compass arrow is drawn pointing the opposite
way, downwind, showing where the air is heading, which is what the Ecowitt
console shows. So an easterly draws an arrow pointing west.

Both conventions are used in the wild, and the difference is only in the
drawing: the degrees are the same either way. The text does not repeat
"from" â€” by convention a wind direction already means the direction it blows
from, so saying it again is redundant. What tells you which way to read the
needle is the needle itself: its tail marks the source and its head the
destination, and both markers carry a tooltip.

**The faint dashed marker is the average direction over the last 10 minutes**,
drawn with the same downwind convention as the solid needle. When the wind is
steady the two overlap; when it is shifting they splay apart, and the angle
between them is a rough read on how variable it is. Both markers carry a
tooltip saying which is which, and the wind card labels the row "10-min avg".

It appears only on compasses of 90px or more â€” the same threshold that governs
the cardinal letters. The weather card's inline compass is 72px, where the
marker was a few faint pixels with no row beside it to explain them, so there
the compass shows the current direction alone.

Two needle shapes are available, on the wind card and on the weather card's
inline compass:

```yaml
needle: arrow      # default â€” hollow ring at the source, solid head downwind
needle: classic    # the original solid pointer
```

`arrow` is the default because its two ends are different kinds of object, so
which end is which stays legible at the weather card's 72px compass, where a
symmetrical shape does not. Both are in the card editor's **Compass needle**
dropdown.
| `ecowitt-rain-card` | Rain rate, a live wet/dry indicator from the piezo sensor, and accumulation bars for the hour, today, 24 hours, the week and the current event |
| `ecowitt-solar-card` | UV index against a banded exposure scale, plus irradiance and illuminance |
| `ecowitt-soil-card` | One soil probe: moisture with a dry/ideal/saturated band, battery, signal and channel |
| `ecowitt-indoor-card` | Gateway indoor temperature and humidity with relative and absolute pressure |

Numbers are punctuated using your Home Assistant number format, so an
illuminance of 74300 reads as `74,300 lx` â€” or `74.300 lx`, `74 300 lx`, or
`74300 lx` if that is what you have set under Profile â†’ Number format. Decimal
places still come from each entity's display precision.

Every value opens Home Assistant's own more-info dialog on tap, so history is
one click away. That includes the large hero readings â€” the temperature, wind
speed, rain rate, UV index and soil moisture â€” and the smaller lines beside
them, such as feels-like and dew point, which each open their own sensor
rather than the card's headline one.

## Install

**Nothing to install.** These cards ship inside the SunSight integration,
which serves them and registers them with the frontend automatically. Install
SunSight (see the [main README](../README.md)) and the cards are available.

There is no Lovelace resource to add â€” the integration serves the file at
`/sunsight/ecowitt-cards.js` and auto-loads it with a `?v=` cache-buster.

After an update, hard-refresh the browser and confirm the
`ECOWITT-CARDS <version>` banner in the console.

If the cards ever fail to appear, check the Home Assistant log: registration
is best-effort and never blocks integration setup, so a failure is logged as a
warning with the path to add manually as a JavaScript Module resource.

## Configure

Add a card from the picker and choose a device â€” that is the only required
option. Each card discovers its own entities from the device you select, so
nothing references an entity id and adding a second soil probe needs no
configuration beyond pointing a new soil card at it.

```yaml
type: custom:ecowitt-weather-card
device: <your WS90 device>
name: Back Garden      # optional, overrides the default title
```

Sub-cards title themselves by subject ("Wind", "Rain", "Solar & UV") so a
dashboard full of them doesn't repeat the device name six times. The overview
and soil cards use the device name, since there the device *is* the subject.
Set `name` to override either.

### Choosing the weather card's tiles

The row of tiles under the temperature is configurable. The card editor lists
the chosen tiles â€” drag them, or use the arrow buttons, to reorder; the âœ•
removes one; the chips underneath add what is left. It follows the same shape
as the tile card's *features* editor.

In YAML it is an ordered list of keys:

```yaml
type: custom:ecowitt-weather-card
device: <your WS90 device>
metrics:
  - hum_out
  - wind_gust
  - rain_daily
  - uv
```

### Custom tiles

A tile isn't limited to the catalogue, or even to the card's device. Click
**Custom entity** in the editor and pick anything from the entity picker, or
write it directly:

```yaml
metrics:
  - hum_out
  - entity: sensor.rainwater_tank_level
  - entity: sensor.pool_temperature
    name: Pool
```

A custom tile takes its label, icon and decimal places from the entity itself,
so it usually needs nothing but the entity id. Give it a `name` to override the
label â€” worth doing, since Home Assistant's friendly names are often long
enough to truncate. Custom and catalogue tiles mix freely and reorder together.

### Renaming a tile

A tile label is a single line and truncates with an ellipsis, so a long
catalogue name such as "Capacitor voltage" gets cut off. Type over the name in
the editor's list to shorten it, or write the entry as an object:

```yaml
metrics:
  - hum_out
  - metric: cap_voltage
    name: Capacitor
```

Bare keys and named entries mix freely, so existing configs keep working. A
name is only stored when it differs from the catalogue default â€” clear the
field and the entry collapses back to a bare key and picks the default up
again, including any later change to it.

Omit `metrics` entirely and you get the default set (humidity, gust, rain
today, rain rate, UV, solar, pressure, VPD) â€” so existing cards are unchanged.
An **empty** list is honoured and shows no tiles at all.

Available keys: `temp_out`, `feels_like`, `dewpoint`, `hum_out`, `wind_speed`,
`wind_gust`, `max_gust`, `wind_dir`, `wind_dir_avg`, `rain_rate`,
`rain_hourly`, `rain_daily`, `rain_24h`, `rain_weekly`, `rain_monthly`,
`rain_yearly`, `rain_event`, `uv`, `solar_rad`, `solar_lux`, `press_rel`,
`press_abs`, `vpd`, `temp_in`, `hum_in`, `soil_moisture`, `battery`, `signal`,
`voltage`, `cap_voltage`.

A tile whose sensor is nowhere to be found is skipped when the card renders,
and the editor marks it *(not on this device)* rather than leaving a silent
gap.

**Hub metrics.** Some readings only exist on the gateway â€” a WS90 has no
barometer, so pressure and the indoor climate belong to the GW2000 that
receives it. The device registry links each sensor to its gateway through
`via_device_id`, and `press_rel`, `press_abs`, `temp_in` and `hum_in` follow
that link when the selected device doesn't report them. So a weather card
pointed at the WS90 still shows pressure.

Only those four keys travel. A blanket fallback would let a card pick up a
sibling's battery or another probe's moisture, so everything else resolves on
the selected device alone.

### Which device goes with which card

The integration exposes one device per physical sensor:

- the **weather station** (WS90/`wh90`) drives the overview, wind, solar and a
  rain card
- a **standalone rain gauge** (WH40/`wh40`) drives its own rain card
- each **soil probe** (`wh51`) drives its own soil card
- the **gateway** (GW2000 etc.) drives the indoor card

If you pick a device with nothing recognisable on it, the card says so rather
than showing a grid of dashes.

### Two rain sources

A WS90 has a piezo rain sensor built in, and a WH40 is a separate tipping
bucket. If you have both, the gateway reports them as two independent blocks
and the integration creates a device for each â€” so they are two rain cards, not
one, and they will not always agree. The piezo reacts faster to the start of
rain; the tipping bucket is the more conventional measure of total
accumulation.

The gateway itself has a rain priority setting that decides which source it
treats as primary for its own reporting and uploads. It does not change what
Home Assistant sees, because the integration exposes both. You can read the
current setting from the gateway directly:

```bash
curl -s http://<gateway-ip>/get_rain_totals
# rainFallPriority: 0 = none, 1 = traditional (WH40), 2 = piezo (WS90)
```

Only the rain card built on the WH40 shows a battery tile, and only the one
built on the WS90 shows the live wet/dry indicator â€” that comes from the piezo's
`srain_piezo` flag, which a tipping bucket doesn't have. Both tiles are driven
by discovery, so each card shows what its device actually has.

## Soil probes that aren't Ecowitt

The soil card works with any soil moisture sensor â€” Zigbee, Z-Wave, rtl_433,
whatever â€” not only an Ecowitt WH51. Its device picker is not restricted to the
Ecowitt integration, so in most cases selecting the device is enough: a moisture
reading and a battery are found the same way they are on a WH51.

Where a device groups things awkwardly, or there is no device at all, name the
entities instead:

```yaml
type: custom:ecowitt-soil-card
name: Sunflower bed
moisture: sensor.sunflower_soil_moisture
battery: sensor.sunflower_battery      # optional
```

`moisture` alone is a complete config â€” `device` becomes optional, and either
entity overrides whatever discovery found. Both are in the card editor.

Pair this with a `scale` suited to the bed in question, since a third-party
probe's percentage is its own scale and won't line up with a WH51's.

## Scales

The soil and solar cards draw a banded track: a coloured axis with a marker
showing where the current reading falls. Both read their bands from config, so
the thresholds are yours to set.

The card editor has a **Scale** section listing the bands â€” threshold, label
and colour per row, with *Add band*, a remove button, an axis maximum, and
*Reset to default*. It opens pre-filled with the card's defaults, and the first
edit writes the whole list into the config. Rows are kept in threshold order,
sorted when a field loses focus rather than mid-keystroke, so a row never jumps
out from under the cursor while you type.

The same thing in YAML:

```yaml
type: custom:ecowitt-soil-card
device: <a soil probe>
scale:
  - to: 12
    label: Water now
    color: error
  - to: 45
    label: Comfortable
    color: success
  - to: 70
    label: Damp
    color: warning
  - label: Too wet          # no `to` â€” runs to the top of the axis
    color: error
```

Each band applies from the previous boundary up to but not including its `to`.
The last band omits `to` and runs to the axis maximum. Bands may be written in
any order; the open-ended one always sorts last.

`color` takes a theme token â€” `success`, `warning`, `error`, `info`, `primary`,
`neutral`, or the aliases `good`, `caution`, `danger` â€” so the card follows the
active theme. Anything else is passed through unchanged if you want a literal.

To move the axis maximum as well, use the object form:

```yaml
scale:
  max: 60
  bands:
    - to: 30
      label: Low
      color: warning
    - label: High
      color: info
```

A malformed `scale` falls back to the card's default rather than rendering a
broken axis.

A band may also carry a `description`, shown as a line of advice under the
reading:

```yaml
scale:
  - to: 3
    label: Low
    color: success
    description: Sun protection not generally required.
```

The UV card ships with these filled in; the soil card leaves them empty, so
the line is hidden until you add one.

### Where the defaults come from

The **UV defaults follow the Bureau of Meteorology's categories** â€” Low 0â€“2,
Moderate 3â€“5, High 6â€“7, Very high 8â€“10, Extreme 11+ â€” and the advice reflects
that BoM issues sun protection times, and ARPANSA and Cancer Council recommend
protection, whenever the index reaches **3 or above**. You shouldn't need to
touch them, but they are overridable like any other scale.

The **soil defaults follow nothing** â€” they are round numbers centred on 50%,
not research.

Two reasons to set your own. A capacitive probe like the WH51 reports a
relative index between its dry and wet calibration points, not volumetric water
content, and Ecowitt provides a custom calibration mode precisely because
different soil types give very different readings at the same real moisture.
And even calibrated, the useful range depends on soil texture and on what is
planted.

For dry-adapted Australian natives â€” banksia, grevillea, hakea and other
Proteaceae â€” sustained wetness is the risk, since it invites *Phytophthora
cinnamomi*, for which there is no effective treatment. A scale that treats the
top of the range as a warning rather than the middle as ideal is likely closer
to what those plants want. Read the band labels as your configuration, not as
horticultural advice.

## Troubleshooting

**A sensor is paired but has no entities.** The integration builds its device
list at setup, so a sensor paired afterwards won't appear until you reload it
(Settings â†’ Devices & Services â†’ Ecowitt Local â†’ Reload). This is not related to
the sensor having no data yet â€” a rain gauge that has seen no rain still reports
zeros, battery and signal.

To check what the gateway itself can see, independent of Home Assistant:

```bash
curl -s "http://<gateway-ip>/get_sensors_info?page=1"   # pages 1..4
```

Entries with an `id` of `FFFFFFFF` are empty slots. Anything with a real id and
an `rssi` is paired and transmitting, whether or not Home Assistant knows about
it.

## How discovery works

Entities are matched by entity id against an ordered rule list, first match
wins, and each key is claimed only once. The ordering matters wherever one id
contains another â€” `soil_moisture_battery` is tested before `soil_moisture`,
`wind_direction_avg` before `wind_direction`, `capacitor_voltage` before
`voltage`. Anything the rules don't recognise falls back to its `device_class`,
so a renamed or newly supported sensor still lands somewhere sensible.

## Development

```bash
node --check custom_components/sunsight/www/ecowitt-cards.js   # syntax
node tests/cards/test_cards.js             # discovery + helper tests
```

The tests evaluate the card file in a `vm` context with the few globals it
touches stubbed, then run discovery against `tests/cards/fixtures/devices.json` â€” a
capture from a real Home Assistant instance. They assert that every entity on
every device is classified and that the ids that contain one another don't
collide. No Home Assistant, no browser, no dependencies.

After pairing new hardware, refresh that fixture so the tests cover it:

```bash
cp .env.example .env    # fill in HA_URL and a long-lived token
python tests/cards/capture_fixture.py
```

`.env` is gitignored and the script never prints the token.

For layout work, serve the repo and open the preview harness, which mounts all
six cards plus a deliberately misconfigured one against the same fixture:

```bash
python -m http.server 8777
# then open http://127.0.0.1:8777/tests/cards/preview.html
```

It stubs `ha-card` and `ha-icon`, and has a dark-mode toggle. Note that icons
render as grey squares there â€” the real MDI glyphs only exist inside Home
Assistant.

## Conventions

- Keep the card dependency-free.
- Use Home Assistant theme variables for colour. The banded scales (UV, soil
  moisture) use `--success-color` / `--warning-color` / `--error-color` /
  `--info-color` rather than fixed hex values, so they follow the active theme.
- Use Home Assistant's typography tokens for type â€” `--ha-font-size-*`,
  `--ha-font-weight-*` â€” never fixed `rem` or `px`. HA multiplies every size by
  `--ha-font-size-scale`, so hardcoded values silently opt out of the user's
  text-size setting. Give each token its HA default as a fallback
  (`var(--ha-font-size-m, 14px)`) so the cards still render on older cores and
  in the preview harness.
- Because type scales, avoid fixed-width columns around text. Prefer
  `max-content` so a row grows with the font instead of clipping. The preview
  harness has a font-scale button for checking this.
- Use `--ha-border-radius-*` for corners (`sm` 4px, `md` 8px, `lg` 12px, `pill`,
  `circle`) rather than literal values.
- Nothing in the file should contain a literal colour, font family, font size,
  font weight or corner radius. To check:

  ```bash
  grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(|font-family|font-(size|weight): [0-9]|border-radius: [0-9]|(gap|padding|margin-top): [0-9]+px" custom_components/sunsight/www/ecowitt-cards.js
  ```

  That includes the startup `console.info`, which is plain text precisely
  because console styling can only take literal colours.
- Use `--ha-space-*` for gaps, padding and margins. It is a 4px scale
  (`--ha-space-1` = 4px, `-2` = 8px, and so on); snap to the nearest step rather
  than reintroducing an off-grid literal.
- **Never rewrite a container's `innerHTML` on every state update.** Home
  Assistant assigns `hass` on every state change, and a weather station emits
  those constantly. Replacing the DOM destroys the node under the user's
  finger, and a click only fires when press and release land on the same
  element â€” so taps get silently swallowed and the control feels dead. Rebuild
  only when the *structure* changes (tracked with a `data-sig` attribute) and
  patch values in place otherwise. `_syncGrid`, `_syncHead` and the equivalents
  in the wind and rain cards do this; the editor guards `_renderMetrics` the
  same way.
- When rows carry a bar or any aligned column, put the grid tracks on the
  **container** and give each row `grid-template-columns: subgrid`. A grid per
  row sizes `max-content` independently, which staggers the bars by label
  length. Subgrid keeps the row a real element, so it stays a single hover and
  click target â€” unlike `display: contents`.
- Bump `CARD_VERSION` on every change so a hard-refresh is verifiable.
