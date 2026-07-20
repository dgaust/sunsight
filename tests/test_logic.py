"""Unit tests for the pure logic.

These deliberately avoid importing Home Assistant. The modules under test
(const, solar, pv_envelope) have no HA dependencies, so they are loaded
directly under a synthetic package name to satisfy their relative imports.

Run with:  python tests/test_logic.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types

CC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "custom_components",
    "sunsight",
)

_pkg = types.ModuleType("ss")
_pkg.__path__ = [CC]
sys.modules["ss"] = _pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"ss.{name}", os.path.join(CC, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"ss.{name}"] = module
    spec.loader.exec_module(module)
    return module


const = _load("const")
solar = _load("solar")
pv_envelope = _load("pv_envelope")
et = _load("evapotranspiration")

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        failures.append(label)


print("clear-sky irradiance")
# Below the horizon there is no clear-sky expectation to compare against.
check("sun below horizon -> 0", solar.clear_sky_ghi(-5) == 0.0)
check("sun at horizon -> 0", solar.clear_sky_ghi(0) == 0.0)
# Sanity anchors: a mid-latitude midday sun should land in the high hundreds.
ghi_45 = solar.clear_sky_ghi(45)
check("45 deg in 700-800 W/m2", 700 < ghi_45 < 800, f"got {ghi_45:.0f}")
check("monotonic with elevation", solar.clear_sky_ghi(20) < solar.clear_sky_ghi(40))

print("\nclear-sky index")
# Reproduces a real reading taken from the author's station: an overcast
# morning measuring 64.96 W/m2 with the sun at 20.78 deg.
index = solar.clear_sky_index(64.96, 20.78)
check("overcast morning ~20%", 15 < index < 25, f"got {index:.1f}")
# 0 rather than None below the horizon: an entity that goes unknown every
# night looks broken, and a flat zero keeps history graphs continuous.
check("low sun -> 0, not None", solar.clear_sky_index(10, 1) == 0.0)
check("night -> 0", solar.clear_sky_index(0, -30) == 0.0)
check("always numeric", isinstance(solar.clear_sky_index(0, -30), float))
# Cloud-edge enhancement can exceed the clear-sky model; report 100, not 140.
check("capped at 100", solar.clear_sky_index(2000, 45) == 100.0)

print("\nazimuth window")
check("inside simple range", solar.in_azimuth_window(280, 235, 320))
check("below simple range", not solar.in_azimuth_window(200, 235, 320))
check("above simple range", not solar.in_azimuth_window(330, 235, 320))
# A north-facing window wraps through 0, which a naive comparison breaks on.
check("wraps through north (350)", solar.in_azimuth_window(350, 340, 20))
check("wraps through north (10)", solar.in_azimuth_window(10, 340, 20))
check("outside wrapped range", not solar.in_azimuth_window(180, 340, 20))

print("\nPV envelope")
env = pv_envelope.PVEnvelope(clip_kw=5.31)
seed_40 = env.seed_for(40)
check("seed is positive at 40 deg", seed_40 > 0, f"got {seed_40:.2f}")
check("seed rises with elevation", env.seed_for(20) < env.seed_for(50))

# Learning: a single high reading must not fully define the envelope.
env2 = pv_envelope.PVEnvelope(clip_kw=5.31)
base = env2.expected(40, 300)
env2.observe(5.0, 40, 300)
after_one = env2.expected(40, 300)
check("damped attack (one spike < full jump)", base < after_one < 5.0,
      f"base {base:.2f} -> {after_one:.2f}")

# Repeated clear readings converge upward.
for _ in range(20):
    env2.observe(5.0, 40, 300)
converged = env2.expected(40, 300)
check("converges on repetition", converged > 4.8, f"got {converged:.2f}")

# Clipping: at the ceiling we can only say "at least clear".
env3 = pv_envelope.PVEnvelope(clip_kw=5.31)
check("clipped reading -> 100%", env3.index(5.31, 60, 0) == 100.0)

# Index behaves sensibly against a known reference.
env4 = pv_envelope.PVEnvelope(clip_kw=5.31)
expected_40 = env4.expected(40, 300)
half = env4.index(expected_40 / 2, 40, 300)
check("half of expected -> ~50%", 45 < half < 55, f"got {half:.1f}")
check("zero output -> 0%", env4.index(0.0, 40, 300) == 0.0)

# Seed acts as a floor so decay can never strand the reference near zero.
env5 = pv_envelope.PVEnvelope(clip_kw=5.31)
env5._bins[env5._key(40, 300)] = 0.01
check("seed floors a decayed bin", env5.expected(40, 300) >= env5.seed_for(40))

# Persistence round-trip.
env6 = pv_envelope.PVEnvelope(clip_kw=5.31)
env6.observe(4.0, 35, 280)
snapshot = env6.as_dict()
env7 = pv_envelope.PVEnvelope(clip_kw=5.31)
env7.load(snapshot)
check("round-trips through storage",
      env7.expected(35, 280) == env6.expected(35, 280))
check("tolerates empty storage", (pv_envelope.PVEnvelope(5.31).load(None) is None))

print("\nevapotranspiration: components")
# FAO-56 Example 3: T = 24.5 degC -> es = 3.075 kPa.
es_24_5 = et.saturation_vapour_pressure(24.5)
check("es(24.5) ~ 3.075 kPa", abs(es_24_5 - 3.075) < 0.01, f"got {es_24_5:.3f}")
# FAO-56 Example 5: T = 30 degC -> slope = 0.2434 kPa/degC.
slope_30 = et.svp_slope(30.0)
check("slope(30) ~ 0.2434", abs(slope_30 - 0.2434) < 0.002, f"got {slope_30:.4f}")
# FAO-56 Example 2: P = 81.8 kPa -> gamma = 0.054 kPa/degC.
gamma = et.psychrometric_constant(81.8)
check("gamma(81.8 kPa) ~ 0.054", abs(gamma - 0.054) < 0.001, f"got {gamma:.4f}")
# FAO-56 Example 14: 3.2 m/s at 10 m -> 2.4 m/s at 2 m.
u2 = et.wind_speed_at_2m(3.2, 10.0)
check("wind 3.2 m/s @10m -> ~2.4 @2m", abs(u2 - 2.4) < 0.05, f"got {u2:.2f}")
check("wind at 2 m unchanged", et.wind_speed_at_2m(3.0, 2.0) == 3.0)

print("\nevapotranspiration: rate")
# A hot, dry, sunny, breezy afternoon should evaporate briskly. FAO-56
# hourly ET0 in these conditions runs a few tenths of a mm per hour.
midday = et.eto_hourly(
    temp_c=30.0, humidity_pct=40.0, wind_ms=2.0, pressure_kpa=101.3,
    solar_wm2=800.0, clear_sky_wm2=850.0, cloudiness_ratio=0.94, is_daytime=True,
)
check("hot sunny afternoon 0.3-0.9 mm/h", 0.3 < midday < 0.9, f"got {midday:.3f}")

# Calm, humid, dark: essentially nothing should evaporate.
night = et.eto_hourly(
    temp_c=12.0, humidity_pct=95.0, wind_ms=0.2, pressure_kpa=101.3,
    solar_wm2=0.0, clear_sky_wm2=0.0, cloudiness_ratio=0.75, is_daytime=False,
)
check("calm humid night ~0 mm/h", 0.0 <= night < 0.05, f"got {night:.4f}")
check("never negative (no 'negative evaporation')", night >= 0.0)

# Overcast must evaporate less than clear sky, all else equal.
overcast = et.eto_hourly(
    temp_c=30.0, humidity_pct=40.0, wind_ms=2.0, pressure_kpa=101.3,
    solar_wm2=200.0, clear_sky_wm2=850.0, cloudiness_ratio=0.24, is_daytime=True,
)
check("overcast < clear", overcast < midday, f"{overcast:.3f} vs {midday:.3f}")

# Wind and dryness both increase demand.
windier = et.eto_hourly(
    temp_c=30.0, humidity_pct=40.0, wind_ms=6.0, pressure_kpa=101.3,
    solar_wm2=800.0, clear_sky_wm2=850.0, cloudiness_ratio=0.94, is_daytime=True,
)
check("windier evaporates more", windier > midday, f"{windier:.3f} vs {midday:.3f}")
humid = et.eto_hourly(
    temp_c=30.0, humidity_pct=90.0, wind_ms=2.0, pressure_kpa=101.3,
    solar_wm2=800.0, clear_sky_wm2=850.0, cloudiness_ratio=0.94, is_daytime=True,
)
check("humid evaporates less", humid < midday, f"{humid:.3f} vs {midday:.3f}")

# Saturated air cannot accept vapour, so the aerodynamic term must vanish.
saturated = et.eto_hourly(
    temp_c=20.0, humidity_pct=100.0, wind_ms=3.0, pressure_kpa=101.3,
    solar_wm2=0.0, clear_sky_wm2=0.0, cloudiness_ratio=0.75, is_daytime=False,
)
check("100% humidity at night -> 0", saturated == 0.0, f"got {saturated:.4f}")

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("all tests passed")
