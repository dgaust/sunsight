# SunSight

A Home Assistant integration that works out **what the sky is actually doing**
from sensors you already own — a light sensor on a window, a weather-station
solar sensor, and your solar PV array.

It answers two questions that are surprisingly hard to get right:

1. **Is direct sun hitting this window right now?** (not "is it daytime", not
   "is it bright" — is the beam actually landing on the glass)
2. **Is it genuinely clear out, or just bright-overcast?**

## Why not just use a lux sensor?

Because raw illuminance lies. Three failure modes this integration exists to
avoid, all of them observed in real data:

- **Cheap outdoor lux sensors saturate.** One tested sensor pegged at ~2960 lx
  on clear days, overcast days, *and during rain*. It could not distinguish
  weather at all — only day from night.
- **Diffuse light is bright.** On a west-facing window, indoor diffuse readings
  reached 619 lx while genuine direct beam ran 700–1772 lx. A threshold picked
  by eye lands in the overlap; a threshold picked from the distributions does not.
- **Light at night isn't sunlight.** A lamp near the sensor produced 5386 lx with
  the sun 29° below the horizon. Any detector without a sun-position gate calls
  that "sunshine".

## How it works

**Sun on window** combines three independent facts: the sun is above the horizon,
its azimuth lies within the window's compass range, and the measured illuminance
exceeds the direct-beam threshold. An optional rain sensor vetoes the result —
in the reference dataset there was never a single beam event while the rain
sensor read wet.

**Clear sky index** compares measured irradiance against the Haurwitz clear-sky
model, `1098·sin(h)·e^(−0.057/sin(h))` W/m². This is self-normalising: it works
at any time of day and any season without calibration, because it asks "what
fraction of the possible sunlight is arriving?" rather than "is it bright?".

**PV clear sky index** does the same using your array. This needs care, because
PV output swings hugely with season — in the reference system, winter peaks ran
about *half* of summer, so no fixed power threshold could ever mean "clear".
Instead SunSight learns the array's own clear-sky envelope per sun-position bin:

- It **seeds** from a physical model (a fitted constant × the clear-sky curve).
- It then **learns** from live data, raising the reference when the array beats
  it, with a damped attack so a single cloud-enhancement spike can't define it.
- It **decays** slowly, so the reference tracks panel soiling, new shade, or
  hardware changes rather than being stuck at a historical best.
- It **ignores clipped readings**: at the inverter ceiling, output reports the
  hardware limit, not the sky.

This means it self-calibrates to *your* roof — tilt, orientation, shading — with
no configuration. It also handles a subtlety a pure physical model gets wrong:
because panels are tilted while the clear-sky model is horizontal, plane-of-array
irradiance exceeds horizontal at low sun. The learner discovers that lift on its own.

## Entities

| Entity | Requires | Meaning |
|---|---|---|
| `binary_sensor.sun_on_window` | window light sensor | Direct sun on the glass |
| `binary_sensor.fine_outdoor_weather` | any clear-sky source | Daylight, dry, measurably sunny |
| `binary_sensor.fine_day_expected` | forecast outlook | Today forecast fine |
| `sensor.clear_sky_index` | irradiance sensor | % of clear-sky irradiance |
| `sensor.pv_clear_sky_index` | PV power sensor | % of the array's clear-sky potential |
| `sensor.evapotranspiration_rate` | irradiance + temp/humidity/wind/pressure | ET₀ in mm/hour |
| `sensor.evapotranspiration_today` | as above | ET₀ accumulated since local midnight |

## Evapotranspiration

If you have a weather station measuring irradiance, temperature, humidity, wind
and pressure, SunSight computes **FAO-56 Penman-Monteith reference
evapotranspiration** — how much water a short grass surface loses to the
atmosphere. It is the standard basis for irrigation scheduling; multiply by a
crop coefficient (Kc) for a particular planting.

The *hourly* FAO-56 formulation (Eq. 53) is used rather than the daily one, so
the sensor reflects current conditions instead of yesterday's averages. The rate
is integrated into a daily total that resets at local midnight and survives
restarts.

Two details worth knowing:

- **Use station (absolute) pressure**, not the sea-level-adjusted figure. The
  equation wants the real air pressure where the water is evaporating.
- **Set your anemometer height.** ET₀ is sensitive to wind, and FAO-56 defines
  it at 2 m; a reading from another height is corrected automatically.

The net-longwave term needs the Rs/Rso cloudiness ratio, which is undefined
after dark. Following FAO-56, SunSight carries forward the last meaningful
daylight ratio rather than dividing by zero.

Every source is optional — the integration degrades to whatever you have. With
only PV you still get a clear-sky index; with only a window sensor you still get
beam detection. When both irradiance and PV are available, irradiance is
preferred for "fine weather" because it measures the sky directly, while PV is an
inference through hardware that can clip, soil, or be shaded.

## Installation

Copy `custom_components/sunsight` into your Home Assistant `config/custom_components`
directory and restart, then add it via **Settings → Devices & Services → Add Integration**.

## Configuration notes

**Window azimuth range** is the compass sector over which the sun can reach the
glass (0=N, 90=E, 180=S, 270=W). Ranges wrapping through north are supported.
Be generous: a west window in the southern hemisphere catches the beam from the
*north-west* in winter (measured: 305–314°) but swings toward true west and
beyond in summer. The default 235–320° covers both.

**Direct sun threshold** should sit in the gap between your diffuse daylight
level and your direct-beam peaks. Watch the window sensor for a few clear and
overcast days and pick a value between the two populations.

**Clear sky threshold** defaults to 70%. Standard clearness-index territory, but
worth checking against what a genuinely clear day reads at your site — sensor
tilt and soiling shift it.

## Credits

Built from a measurement study rather than guesswork; the defaults in `const.py`
carry comments noting which numbers came from data and which from first principles.
