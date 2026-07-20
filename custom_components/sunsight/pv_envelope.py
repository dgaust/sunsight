"""Self-calibrating clear-sky envelope for PV generation.

Why this exists: PV output varies enormously with season (measured: winter
peaks run roughly half of summer), so no fixed power threshold can mean
"the sky is clear". What *is* stable is output relative to the best this
array achieves at a given sun position. This class tracks that reference.

The reference starts from a physical seed (a fitted constant times the
Haurwitz clear-sky curve) and is then refined from live data, so it adapts
to panel soiling, seasonal shading, and array changes without the user ever
calibrating anything.
"""

from __future__ import annotations

import logging
import time

from .const import (
    PV_DECAY_PER_DAY,
    PV_LEARN_ALPHA,
    SEED_PV_FACTOR,
)
from .solar import clear_sky_ghi, sun_bin

_LOGGER = logging.getLogger(__name__)

_SECONDS_PER_DAY = 86400.0


class PVEnvelope:
    """Tracks the best-observed PV output per sun-position bin."""

    def __init__(self, clip_kw: float) -> None:
        self._clip_kw = clip_kw
        self._bins: dict[str, float] = {}
        self._last_decay: float = time.time()

    # -- reference ------------------------------------------------------

    def seed_for(self, elevation: float) -> float:
        """Physical fallback for a bin we have not learned yet."""
        return SEED_PV_FACTOR * clear_sky_ghi(elevation)

    def expected(self, elevation: float, azimuth: float) -> float | None:
        """Expected clear-sky PV output (kW) at this sun position.

        The seed acts as a floor rather than merely a default. A learned
        value can only have come from real output, but a long cloudy spell
        plus decay could drag it below what the array demonstrably manages,
        so we never return less than the physical estimate.
        """
        seed = self.seed_for(elevation)
        if seed <= 0:
            return None
        learned = self._bins.get(self._key(elevation, azimuth))
        expected = max(learned, seed) if learned is not None else seed
        return min(expected, self._clip_kw)

    def index(self, power_kw: float, elevation: float, azimuth: float) -> float | None:
        """Measured PV as a percentage of the clear-sky expectation."""
        expected = self.expected(elevation, azimuth)
        if not expected:
            return None
        # A clipping inverter cannot report how clear the sky *really* is,
        # only that it is at least clear enough to saturate the array.
        if power_kw >= self._clip_kw * 0.99:
            return 100.0
        return min(power_kw / expected * 100.0, 100.0)

    # -- learning -------------------------------------------------------

    def observe(self, power_kw: float, elevation: float, azimuth: float) -> None:
        """Fold a live reading into the envelope."""
        self._apply_decay()

        # Never learn from a clipped reading: it reflects the inverter limit,
        # not what the sky delivered.
        if power_kw >= self._clip_kw:
            power_kw = self._clip_kw

        key = self._key(elevation, azimuth)
        current = self._bins.get(key, self.seed_for(elevation))
        if power_kw > current:
            # Damped attack, so one cloud-enhancement spike cannot define
            # the envelope on its own; a genuinely clear day repeats and
            # converges within a handful of samples.
            self._bins[key] = current + PV_LEARN_ALPHA * (power_kw - current)

    def _apply_decay(self) -> None:
        """Bleed the references down slowly so they can track real losses."""
        now = time.time()
        elapsed_days = (now - self._last_decay) / _SECONDS_PER_DAY
        if elapsed_days <= 0:
            return
        # Decaying more often than daily just adds float noise.
        if elapsed_days < 1.0:
            return
        factor = PV_DECAY_PER_DAY**elapsed_days
        for key in self._bins:
            self._bins[key] *= factor
        self._last_decay = now

    @staticmethod
    def _key(elevation: float, azimuth: float) -> str:
        elev_bin, az_bin = sun_bin(elevation, azimuth)
        return f"{elev_bin}:{az_bin}"

    # -- persistence ----------------------------------------------------

    @property
    def learned_bins(self) -> int:
        return len(self._bins)

    def as_dict(self) -> dict:
        return {"bins": self._bins, "last_decay": self._last_decay}

    def load(self, data: dict | None) -> None:
        if not data:
            return
        bins = data.get("bins")
        if isinstance(bins, dict):
            self._bins = {
                key: float(value)
                for key, value in bins.items()
                if isinstance(value, (int, float))
            }
        last = data.get("last_decay")
        if isinstance(last, (int, float)):
            self._last_decay = float(last)
        _LOGGER.debug("Restored PV envelope with %d bins", len(self._bins))
