"""FAO-56 Penman-Monteith reference evapotranspiration.

Implements the *hourly* form (FAO-56 Eq. 53), which suits a live sensor far
better than the daily form: it uses instantaneous readings and yields a rate
in mm/hour that can be integrated into a daily total.

Reference: Allen, R.G. et al. (1998), "Crop evapotranspiration - Guidelines
for computing crop water requirements", FAO Irrigation and Drainage Paper 56.

ET0 is the reference value for a hypothetical short green grass surface. It
is what irrigation scheduling is normally based on; multiply by a crop
coefficient (Kc) for a specific planting.

Kept free of Home Assistant imports so it can be unit-tested standalone.
"""

from __future__ import annotations

import math

# Albedo of the FAO reference grass surface.
ALBEDO = 0.23

# Stefan-Boltzmann constant expressed per hour [MJ K^-4 m^-2 hour^-1].
STEFAN_BOLTZMANN_HOURLY = 2.043e-10

# 1 W/m^2 sustained for an hour = 3600 J/m^2 = 0.0036 MJ/m^2.
WM2_TO_MJ_PER_HOUR = 0.0036


def saturation_vapour_pressure(temp_c: float) -> float:
    """Saturation vapour pressure at a given temperature [kPa] (Eq. 11)."""
    return 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))


def svp_slope(temp_c: float) -> float:
    """Slope of the saturation vapour pressure curve [kPa/degC] (Eq. 13)."""
    return 4098.0 * saturation_vapour_pressure(temp_c) / (temp_c + 237.3) ** 2


def psychrometric_constant(pressure_kpa: float) -> float:
    """Psychrometric constant [kPa/degC] (Eq. 8)."""
    return 0.000665 * pressure_kpa


def wind_speed_at_2m(speed_ms: float, height_m: float) -> float:
    """Adjust a wind measurement to the 2 m reference height (Eq. 47).

    Anemometers are rarely at exactly 2 m, and ET0 is sensitive to wind, so
    this correction matters for a roof- or pole-mounted station.
    """
    if height_m <= 0 or abs(height_m - 2.0) < 0.01:
        return speed_ms
    return speed_ms * 4.87 / math.log(67.8 * height_m - 5.42)


def net_radiation(
    solar_mj: float,
    clear_sky_mj: float,
    temp_c: float,
    actual_vp_kpa: float,
    cloudiness_ratio: float,
) -> float:
    """Net radiation at the grass surface [MJ m^-2 hour^-1] (Eqs. 38-40).

    `cloudiness_ratio` is Rs/Rso, the fraction of clear-sky radiation actually
    received. It is passed in rather than derived here because at night both
    Rs and Rso are zero; FAO-56 directs you to carry forward the ratio from
    the last few daylight hours instead of dividing by zero.
    """
    # Net shortwave: what the surface absorbs after reflection.
    net_shortwave = (1.0 - ALBEDO) * solar_mj

    # Net longwave: heat radiated back to a sky that is drier and clearer.
    temp_k = temp_c + 273.16
    ratio = min(max(cloudiness_ratio, 0.25), 1.0)
    net_longwave = (
        STEFAN_BOLTZMANN_HOURLY
        * temp_k**4
        * (0.34 - 0.14 * math.sqrt(max(actual_vp_kpa, 0.0)))
        * (1.35 * ratio - 0.35)
    )
    return net_shortwave - net_longwave


def eto_hourly(
    temp_c: float,
    humidity_pct: float,
    wind_ms: float,
    pressure_kpa: float,
    solar_wm2: float,
    clear_sky_wm2: float,
    cloudiness_ratio: float,
    is_daytime: bool,
    wind_height_m: float = 2.0,
) -> float:
    """Reference evapotranspiration [mm/hour] (FAO-56 Eq. 53).

    Returns 0 rather than a negative number: the equation can go slightly
    negative on calm humid nights, which physically means condensation
    (dew forming) rather than evaporation.
    """
    solar_mj = solar_wm2 * WM2_TO_MJ_PER_HOUR
    clear_sky_mj = clear_sky_wm2 * WM2_TO_MJ_PER_HOUR

    delta = svp_slope(temp_c)
    gamma = psychrometric_constant(pressure_kpa)

    es = saturation_vapour_pressure(temp_c)
    ea = es * min(max(humidity_pct, 0.0), 100.0) / 100.0
    vapour_deficit = max(es - ea, 0.0)

    rn = net_radiation(solar_mj, clear_sky_mj, temp_c, ea, cloudiness_ratio)

    # Soil heat flux. Over an hour it is a meaningful fraction of Rn, and it
    # differs between day and night because the ground stores heat by day and
    # releases it after dark.
    g = 0.1 * rn if is_daytime else 0.5 * rn

    u2 = wind_speed_at_2m(wind_ms, wind_height_m)

    numerator = 0.408 * delta * (rn - g) + gamma * (37.0 / (temp_c + 273.0)) * u2 * vapour_deficit
    denominator = delta + gamma * (1.0 + 0.34 * u2)
    if denominator <= 0:
        return 0.0
    return max(numerator / denominator, 0.0)
