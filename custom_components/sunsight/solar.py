"""Pure solar helpers.

Deliberately free of Home Assistant imports so the maths can be unit-tested
without a running HA instance.
"""

from __future__ import annotations

import math

from .const import HAURWITZ_A, HAURWITZ_B, PV_AZ_BIN, PV_ELEV_BIN


def clear_sky_ghi(elevation_deg: float) -> float:
    """Clear-sky global horizontal irradiance in W/m^2 (Haurwitz model).

    Returns 0.0 for a sun at or below the horizon, and for the few degrees
    above it where the exponential term makes the model unstable.
    """
    sin_h = math.sin(math.radians(elevation_deg))
    if sin_h <= 0.05:
        return 0.0
    return HAURWITZ_A * sin_h * math.exp(-HAURWITZ_B / sin_h)


def clear_sky_index(measured_wm2: float, elevation_deg: float) -> float:
    """Measured irradiance as a percentage of the clear-sky expectation.

    Returns 0 when the sun is too low for the ratio to mean anything, rather
    than nothing at all. Overnight there is genuinely no sunlight arriving,
    and a flat zero keeps history graphs continuous; an entity that goes
    unknown every night reads as broken even when it is working perfectly.
    A source sensor that is actually unavailable is a different matter, and
    callers report that as unknown so real faults stay visible.

    Capped at 100: cloud-edge enhancement can genuinely exceed clear-sky
    irradiance, but reporting >100% "clear" would confuse more than it helps.
    """
    expected = clear_sky_ghi(elevation_deg)
    if expected <= 0:
        return 0.0
    return min(measured_wm2 / expected * 100.0, 100.0)


def sun_bin(elevation_deg: float, azimuth_deg: float) -> tuple[int, int]:
    """Bin a sun position for envelope lookup."""
    elev_bin = int(elevation_deg // PV_ELEV_BIN) * PV_ELEV_BIN
    az_bin = int(azimuth_deg % 360 // PV_AZ_BIN) * PV_AZ_BIN
    return elev_bin, az_bin


def in_azimuth_window(azimuth_deg: float, az_min: float, az_max: float) -> bool:
    """Is the sun within a window's azimuth range?

    Handles ranges that wrap through north (e.g. 340 -> 20), which a naive
    min <= x <= max comparison would get wrong for north-facing windows.
    """
    az = azimuth_deg % 360
    lo = az_min % 360
    hi = az_max % 360
    if lo <= hi:
        return lo <= az <= hi
    return az >= lo or az <= hi
