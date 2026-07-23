"""Constants and tuning values for SunSight.

The defaults here are not guesses: they were derived from ~8.5 months of the
author's own long-term statistics (PV generation) plus a validated 11-day study
of an indoor window luminance sensor against computed sun position. Where a
number came from measurement rather than first principles, the comment says so.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "sunsight"

PLATFORMS: Final = ["binary_sensor", "sensor"]

# Mirrors CARD_VERSION in www/ecowitt-cards.js. The two must be bumped
# together: this copy is the ?v= cache-buster on the auto-loaded URL, so
# leaving it stale means browsers keep serving the old card.
CARD_VERSION: Final = "1.21.0"
CARD_FILENAME: Final = "ecowitt-cards.js"

# --- configuration keys -------------------------------------------------

CONF_WINDOW_LUX: Final = "window_lux_entity"
CONF_WINDOW_AZ_MIN: Final = "window_azimuth_min"
CONF_WINDOW_AZ_MAX: Final = "window_azimuth_max"
CONF_WINDOW_LUX_THRESHOLD: Final = "window_lux_threshold"
CONF_IRRADIANCE: Final = "irradiance_entity"
CONF_PV_POWER: Final = "pv_power_entity"
CONF_PV_CLIP: Final = "pv_clip_kw"
CONF_RAIN: Final = "rain_entity"
CONF_FORECAST_OUTLOOK: Final = "forecast_outlook_entity"
CONF_FORECAST_RAIN_CHANCE: Final = "forecast_rain_chance_entity"
CONF_CLEAR_THRESHOLD: Final = "clear_threshold"
CONF_MIN_ELEVATION: Final = "min_elevation"

# --- window beam detection ---------------------------------------------
#
# Measured: over 11 days every genuine direct-sun event on a west-facing
# window fell between azimuth 305-314 deg at 8-16 deg elevation (winter).
# The default range is deliberately wider than the winter beam so the same
# config still holds in summer, when the sun swings toward true west (270)
# and beyond. Diffuse light never exceeded 619 lx while a real beam ran
# 700-1772 lx, so 700 sits in a wide empty gap between the two populations.

DEFAULT_WINDOW_AZ_MIN: Final = 235.0
DEFAULT_WINDOW_AZ_MAX: Final = 320.0
DEFAULT_WINDOW_LUX_THRESHOLD: Final = 700.0

# --- clear sky ----------------------------------------------------------
#
# Haurwitz clear-sky global horizontal irradiance:
#     GHI = 1098 * sin(h) * exp(-0.057 / sin(h))   [W/m^2]
# A standard model requiring no site calibration. Only the *threshold* for
# calling a sky "clear" is site-dependent.

HAURWITZ_A: Final = 1098.0
HAURWITZ_B: Final = 0.057

# Below this the clear-sky model is numerically unstable (sin(h) -> 0) and
# the resulting index becomes meaningless.
MIN_INDEX_ELEVATION: Final = 5.0

DEFAULT_CLEAR_THRESHOLD: Final = 70.0
DEFAULT_MIN_ELEVATION: Final = 5.0

# --- PV clear-sky envelope ---------------------------------------------
#
# Expected clear-sky PV is modelled as  factor * haurwitz(elevation),
# capped at the array's clipping ceiling. The seed factor is the p90 of
# measured (PV / haurwitz) across ~2600 unclipped daylight hours; per-azimuth
# fitted values spanned 0.00528-0.00577, i.e. within +/-5%, so a single
# scalar is used and any genuine asymmetry is left for the learner to find.
#
# Note this seed *under*-estimates below ~15 deg elevation, because Haurwitz
# is horizontal irradiance while panels are tilted (plane-of-array irradiance
# exceeds horizontal at low sun). The runtime learner corrects this upward.

SEED_PV_FACTOR: Final = 0.0055

# Observed peak output; readings at or above this are treated as clipped and
# reported as fully clear rather than as an exact ratio.
DEFAULT_PV_CLIP_KW: Final = 5.31

# Sun-position bin sizes for the learned envelope.
PV_ELEV_BIN: Final = 5
PV_AZ_BIN: Final = 20

# Learning behaviour. Attack is damped so a single cloud-enhancement spike
# cannot define the envelope; decay lets the reference fall back over time
# for panel soiling, new shading, or hardware changes.
PV_LEARN_ALPHA: Final = 0.30
PV_DECAY_PER_DAY: Final = 0.995

# Don't learn or report a PV index when the sun is too low: output is tiny,
# noisy, and dominated by horizon obstructions.
PV_MIN_ELEVATION: Final = 8.0

# Storage
STORAGE_KEY: Final = f"{DOMAIN}.pv_envelope"
STORAGE_VERSION: Final = 1
SAVE_DELAY: Final = 300

# --- plain-English sunlight description ---------------------------------
#
# The numeric index is precise but not readable at a glance, and a bare 0
# overnight tells you nothing about *why*. These labels describe how much
# sunlight is actually available.
#
# The boundaries are drawn from measured data rather than picked evenly:
# clear days read 92-96, dry overcast 44-59, and rain 29-30, so the labels
# line up with conditions that were actually observed.

# Civil twilight. Below this there is no useful daylight at all.
TWILIGHT_ELEVATION: Final = -6.0

SUNLIGHT_DARKNESS: Final = "Darkness"
# The twilight band is split by whether the sun is climbing or sinking, so
# "Twilight" in the morning reads as "Dawn" and in the evening as "Dusk".
SUNLIGHT_DAWN: Final = "Dawn"
SUNLIGHT_DUSK: Final = "Dusk"
# Fallback for the rare case the sun's rising/setting direction is unknown;
# kept only so the enum has a valid value to report then.
SUNLIGHT_TWILIGHT: Final = "Twilight"

# Ordered high to low; the first threshold the index meets or exceeds wins.
SUNLIGHT_LEVELS: Final = (
    (88.0, "Full sunshine"),
    (75.0, "Hazy sunshine"),
    (60.0, "Partly cloudy"),
    (45.0, "Cloudy"),
    (25.0, "Overcast"),
    (0.0, "Heavy cloud"),
)

# Every value the sensor can report, for the enum device class.
SUNLIGHT_OPTIONS: Final = [
    SUNLIGHT_DARKNESS,
    SUNLIGHT_DAWN,
    SUNLIGHT_DUSK,
    SUNLIGHT_TWILIGHT,
    *[label for _, label in reversed(SUNLIGHT_LEVELS)],
]

# --- evapotranspiration -------------------------------------------------

CONF_TEMPERATURE: Final = "temperature_entity"
CONF_HUMIDITY: Final = "humidity_entity"
CONF_WIND_SPEED: Final = "wind_speed_entity"
CONF_PRESSURE: Final = "pressure_entity"
CONF_WIND_HEIGHT: Final = "wind_height_m"

# FAO-56 defines wind at 2 m; readings from another height are corrected.
DEFAULT_WIND_HEIGHT: Final = 2.0

# At night Rs and Rso are both zero, so the Rs/Rso cloudiness ratio cannot be
# computed. FAO-56 says to carry forward the value from the last daylight
# hours; this is the fallback used before any daylight has been seen.
DEFAULT_CLOUDINESS_RATIO: Final = 0.75

# Only trust the measured ratio when there is enough sun for it to be
# meaningful - near sunrise/sunset the quotient is dominated by noise.
CLOUDINESS_MIN_CLEAR_SKY: Final = 50.0

# Cap a single integration step. Without this, a restart or a stalled sensor
# would fold hours of elapsed time into one reading and inflate the daily
# total with a rate that was only ever sampled once.
ET_MAX_STEP_HOURS: Final = 0.25

# --- forecast -----------------------------------------------------------

FINE_OUTLOOKS: Final = frozenset({"sunny", "mostly_sunny", "clear", "mostly_clear"})
DEFAULT_FORECAST_RAIN_MAX: Final = 40.0
