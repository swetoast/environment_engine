"""A learned thermal model of the room (pure, no dependencies).

Instead of a single "it warms at X °C/min" number, this fits the actual physics:

    dT/dt = k*(T_out - T_in) + s*solar + c*cooling + o*occupied + b

  k  -- envelope leakiness (how fast outdoor temperature bleeds in). 1/k is the room's
        thermal time constant tau, i.e. how sluggish it is.
  s  -- solar gain per unit of sun (from lux / sun elevation).
  c  -- the AC's effective cooling power (negative).
  o  -- the heat *you* add: bodies, cooking, screens. An empty home and an occupied one are
        genuinely different thermal systems, so they get their own term rather than being
        blurred into one average that is wrong in both states.
  b  -- the standing internal gain that is there regardless (fridge, standby electronics).

An empty house is the cleanest laboratory there is -- no doors, no cooking, no bodies -- so the
model keeps learning while you are away rather than sleeping. It just needs to know you are out.

The coefficients are fitted online with recursive least squares (a forgetting factor
keeps it adapting as seasons and furniture change). Readings are first folded into
ten-minute windows: a 0.1 °C sensor read once a minute reports a rate of either 0 or
0.1 °C/min, which is quantisation noise fifty times larger than the real drift, and a fit
made on that never becomes trustworthy.

Two things are learned beside the fit, because one coefficient cannot hold them:
the sun gain by hour of day (a west-facing room takes its heat at 17:00, not at noon) and
the gap between the unit's own sensor and the room sensor. That makes the model
*predictive*: given the weather forecast it can answer "if I do nothing, what will
this room read in 30 minutes?" rather than extrapolating a straight line.

Until it has enough clean evidence it does not pretend to know: `confidence` stays low
and callers fall back to `BucketedRates`, a simple context-keyed average (sun up/down x
outdoor warmer/cooler) that is useful from the very first day.
"""
from __future__ import annotations

_N = 5                     # k, s, c, o, b
_FORGET = 0.997            # forgetting factor: adapt without thrashing
_MAX_DT = 30.0             # minutes; longer gaps mean a restart/outage, not physics
_WINDOW = 10.0             # minutes of clean data folded into ONE fitted sample
_WARMUP = 20               # fitted windows before the model is trusted at all
_TRUSTED = 60              # fitted windows for full confidence
_PEAK_SMOOTHING = 0.05     # the "best ever" rate follows a sustained level, not one lucky fit
_SUN_HOUR_MIN = 6          # windows seen at an hour of day before its learned sun gain is used
_OFFSET_MIN = 20           # readings before the unit-sensor offset is trusted

# Physically sane bounds -- a bad fit must never produce nonsense control.
_K_RANGE = (0.0, 0.05)     # per minute, per °C of indoor/outdoor difference
_C_RANGE = (-0.5, 0.0)     # the engine only cools; this coefficient is cooling-only
_B_RANGE = (-0.2, 0.2)
_S_RANGE = (0.0, 0.5)
_O_RANGE = (0.0, 0.2)      # people add heat; they never chill a room


def _clamp(value, low, high):
    return max(low, min(value, high))


class BucketedRates:
    """Context-keyed drift rates: what the room does with the sun up vs down, and with
    the outdoors warmer vs cooler. Crude but honest, and useful immediately."""

    def __init__(self) -> None:
        self.rates: dict[str, float] = {}
        self.counts: dict[str, int] = {}

    @staticmethod
    def key(sun_up: bool, outdoor_warmer: bool) -> str:
        return f"{'sun' if sun_up else 'dark'}_{'warm' if outdoor_warmer else 'cool'}"

    def update(self, key: str, rate: float, alpha: float = 0.2) -> None:
        current = self.rates.get(key, rate)
        self.rates[key] = (1.0 - alpha) * current + alpha * rate
        self.counts[key] = self.counts.get(key, 0) + 1

    def rate(self, key: str) -> float:
        return self.rates.get(key, 0.0)

    def samples(self, key: str) -> int:
        return self.counts.get(key, 0)


class ThermalModel:
    def __init__(self) -> None:
        self.theta = [0.0] * _N                       # k, s, c, o, b
        self.p = [[1000.0 if i == j else 0.0 for j in range(_N)] for i in range(_N)]
        self.samples = 0
        self.rejected = 0
        self._residual_var = 0.0
        self.buckets = BucketedRates()
        self.cooling_effect: dict[str, float] = {}    # °C/min removed, by outdoor band
        self._cooling_counts: dict[str, int] = {}
        self.struggling = False                       # cooling, but the room still gains
        self._residual_ema = 0.0                      # persistent, *signed* model error
        self._noise_var = 0.0                         # baseline noise, measured in quiet times only
        self.peak_effort = 0.0                        # best SUSTAINED |conditioning rate| this room has shown
        self._effort_ema = 0.0
        self.sun_gain: dict[int, float] = {}          # hour of day -> °C/min the sun adds then
        self._sun_counts: dict[int, int] = {}
        self.unit_offset = 0.0                        # unit sensor minus room sensor, while cooling
        self._offset_count = 0
        self._window = None                           # the window being accumulated

    # ---------- fitting ----------
    def update(self, previous, current, dt_minutes: float, cooling: bool, solar: float,
               hour: int | None = None) -> bool:
        """Feed one interval. Returns True when a window completed and was fitted.

        Intervals are accumulated into a window of about ten minutes and the window is fitted
        as one sample: its start-to-end temperature change against the time-weighted average
        of everything that drove it. A dirty interval (open window, sensor glitch, restart
        gap, someone arriving) discards the window in progress, so nothing ambiguous is ever
        learned from. A compressor switching on or off inside a window is fine: `cooling`
        enters as the fraction of the window it ran.
        """
        if not self._clean(previous, current, dt_minutes):
            self.rejected += 1
            self._window = None
            return False
        w = self._window
        if w is None:
            w = self._window = {"start": previous.indoor_temp, "minutes": 0.0, "gap": 0.0, "solar": 0.0,
                                "cooling": 0.0, "occupied": 0.0, "outdoor": 0.0, "sun_up": 0.0}
        w["minutes"] += dt_minutes
        w["gap"] += (previous.outdoor_temp - previous.indoor_temp) * dt_minutes
        w["solar"] += solar * dt_minutes
        w["cooling"] += dt_minutes if cooling else 0.0
        w["occupied"] += dt_minutes if getattr(previous, "occupancy", False) else 0.0
        w["outdoor"] += previous.outdoor_temp * dt_minutes
        w["sun_up"] += dt_minutes if previous.sun_up else 0.0
        if w["minutes"] < _WINDOW:
            return False
        self._window = None
        minutes = w["minutes"]
        rate = (current.indoor_temp - w["start"]) / minutes               # °C per minute
        gap, sun, cool, occupied = w["gap"] / minutes, w["solar"] / minutes, w["cooling"] / minutes, w["occupied"] / minutes
        outdoor = w["outdoor"] / minutes
        sun_up = w["sun_up"] >= minutes / 2
        self._rls([gap, sun, cool, occupied, 1.0], rate)
        self.samples += 1
        # Context bucket (works from day one, and is the fallback while the model warms up).
        if cool == 0.0:
            self.buckets.update(self.buckets.key(sun_up, gap > 0), rate)
        if cool >= 0.9:
            self._record_cooling(rate, outdoor)
        # What the sun adds at THIS hour: whatever the window gained beyond the envelope,
        # the people and the standing load, with the compressor off.
        if hour is not None and sun_up and cool == 0.0 and self.confidence > 0.0:
            implied = rate - (self.leakiness * gap + self.occupied_gain * occupied + self.internal_gain)
            implied = _clamp(implied, 0.0, _S_RANGE[1])
            seen = self._sun_counts.get(hour, 0)
            self.sun_gain[hour] = implied if seen == 0 else 0.8 * self.sun_gain[hour] + 0.2 * implied
            self._sun_counts[hour] = seen + 1
        return True

    def observe_unit_sensor(self, offset: float | None, cooling: bool) -> None:
        """Learn how far the unit's own sensor sits from the room sensor while it is cooling,
        which is the only time the unit acts on it."""
        if offset is None or not cooling or abs(offset) > 10.0:
            return
        self.unit_offset = offset if self._offset_count == 0 else 0.95 * self.unit_offset + 0.05 * offset
        self._offset_count += 1

    @property
    def setpoint_compensation(self) -> int:
        """Whole degrees to take OFF the setpoint sent to the unit, because its own sensor
        reads colder than the room. Such a unit reaches "22" on its sensor and idles while
        the room is still 24, so it has to be asked for less. A unit that reads WARMER than
        the room needs nothing: it simply keeps running until the engine stops it. Never
        negative, so it can only ever make the unit cool harder."""
        if self._offset_count < _OFFSET_MIN or self.unit_offset >= 0.0:
            return 0
        return int(min(-self.unit_offset, 3.0))

    def learned_sun(self, hour: int | None) -> float | None:
        """°C/min the sun adds at this hour of day, once that hour has been seen enough."""
        if hour is None or self._sun_counts.get(hour, 0) < _SUN_HOUR_MIN:
            return None
        return self.sun_gain[hour]

    @property
    def sun_peak_hour(self) -> int | None:
        hours = {h: g for h, g in self.sun_gain.items() if self._sun_counts.get(h, 0) >= _SUN_HOUR_MIN}
        if not hours or max(hours.values()) <= 0.0:
            return None
        return max(hours, key=hours.get)

    def _clean(self, previous, current, dt_minutes: float) -> bool:
        if previous is None or current is None:
            return False
        if not (0.0 < dt_minutes <= _MAX_DT):
            return False                                   # restart / outage / clock jump
        if previous.indoor_temp is None or current.indoor_temp is None or previous.outdoor_temp is None:
            return False
        # A dropped temperature sensor reports a substituted 0 °C, which looks perfectly
        # calm sample-to-sample: no spike, sane timing. Learning from it teaches the model
        # that the room sits at 0 °C and never moves. Trust the validity flag.
        if not getattr(previous, "temperature_valid", True) or not getattr(current, "temperature_valid", True):
            return False
        if previous.window_open or current.window_open:
            return False                                   # uncontrolled air exchange
        if abs(current.indoor_temp - previous.indoor_temp) > 5.0:
            return False                                   # sensor glitch, not a room
        if getattr(previous, "occupancy", None) != getattr(current, "occupancy", None):
            return False                                   # someone came or went mid-interval
        return True

    def _rls(self, x: list[float], y: float) -> None:
        px = [sum(self.p[i][j] * x[j] for j in range(_N)) for i in range(_N)]
        xpx = sum(x[i] * px[i] for i in range(_N))
        denominator = _FORGET + xpx
        if denominator <= 1e-9:
            return
        gain = [px[i] / denominator for i in range(_N)]
        error = y - sum(x[i] * self.theta[i] for i in range(_N))
        for i in range(_N):
            self.theta[i] += gain[i] * error
        for i in range(_N):
            for j in range(_N):
                self.p[i][j] = (self.p[i][j] - gain[i] * px[j]) / _FORGET
        self._residual_var = 0.95 * self._residual_var + 0.05 * (error * error)
        # A one-off error is noise. An error that keeps pointing the same way is the room
        # doing something the physics can't explain -- that's the interesting signal.
        self._residual_ema = 0.85 * self._residual_ema + 0.15 * error
        # Track the best conditioning rate this room has ever shown, once there's enough
        # evidence to trust it. Effectiveness is measured against THIS -- the room's own
        # proven best -- not an assumed "healthy unit" rate, so it works for any hardware:
        # a tiny bedroom unit, a whole-house system, or a heat pump warming rather than
        # cooling. The magnitude is direction-agnostic; |c| covers cool and heat alike.
        # "Best" means a level the unit SUSTAINED. Taking the raw maximum let a single noisy
        # fit set a bar the unit could never reach again, which read as permanent decline.
        if self.confidence >= 0.5:
            effort = abs(self.cooling_power)
            self._effort_ema = effort if self._effort_ema == 0.0 else (1 - _PEAK_SMOOTHING) * self._effort_ema + _PEAK_SMOOTHING * effort
            self.peak_effort = max(self.peak_effort, self._effort_ema)
        # The yardstick has to be the room's *quiet* noise. Folding the anomaly into the
        # same variance we measure it against would let a big enough event hide inside its
        # own inflated error bars, so ordinary-looking errors update the baseline and
        # outliers are left out of it.
        sigma = max(self._noise_var ** 0.5, 1e-4)
        if self._noise_var == 0.0 or abs(error) < 3.0 * sigma:
            self._noise_var = 0.98 * self._noise_var + 0.02 * (error * error)

    def _record_cooling(self, rate: float, outdoor: float) -> None:
        band = self.outdoor_band(outdoor)
        removed = max(0.0, -rate)                          # °C/min the AC actually took out
        current = self.cooling_effect.get(band, removed)
        self.cooling_effect[band] = 0.8 * current + 0.2 * removed
        self._cooling_counts[band] = self._cooling_counts.get(band, 0) + 1
        # Compressor running yet the room still gains heat: undersized, dirty filter,
        # a door left open, or simply a losing battle against the outdoors.
        self.struggling = rate > 0.005

    @staticmethod
    def outdoor_band(outdoor: float) -> str:
        if outdoor is None:
            return "unknown"
        if outdoor < 20:
            return "<20C"
        if outdoor < 25:
            return "20-25C"
        if outdoor < 30:
            return "25-30C"
        return ">30C"

    # ---------- what it learned ----------
    @property
    def leakiness(self) -> float:
        return _clamp(self.theta[0], *_K_RANGE)

    @property
    def solar_gain(self) -> float:
        return _clamp(self.theta[1], *_S_RANGE)

    @property
    def cooling_power(self) -> float:
        return _clamp(self.theta[2], *_C_RANGE)

    @property
    def occupied_gain(self) -> float:
        """Extra °C/min the room gains simply because someone is home."""
        return _clamp(self.theta[3], *_O_RANGE)

    @property
    def internal_gain(self) -> float:
        return _clamp(self.theta[4], *_B_RANGE)

    @property
    def time_constant(self) -> float | None:
        """Tau in minutes: how sluggish the room is. A big tau coasts for a long time."""
        k = self.leakiness
        return None if k <= 1e-4 else min(1.0 / k, 720.0)

    @property
    def confidence(self) -> float:
        """0..1 -- how much the engine should trust this model over the simple fallback."""
        if self.samples < _WARMUP:
            return 0.0
        coverage = min((self.samples - _WARMUP) / (_TRUSTED - _WARMUP), 1.0)
        noise = 1.0 / (1.0 + 400.0 * self._residual_var)   # tighter residuals -> more trust
        return _clamp(coverage * noise, 0.0, 1.0)

    @property
    def effectiveness(self) -> float:
        """0..1 -- how well the climate system is performing RIGHT NOW relative to the best
        this room has ever shown, load controlled for. Direction-agnostic: it reads the same
        whether a unit is cooling or a heat pump is heating, because it compares the current
        conditioning rate against the room's own proven peak rather than an assumed ideal.

        100% means "as good as this room gets"; a sustained drop is the useful signal -- a
        clogging filter, a door left open, a failing compressor. Returns 0.5 (neutral) until
        there is a trustworthy baseline to measure against, so it never accuses new hardware.
        """
        if self.confidence <= 0.0 or self.peak_effort <= 1e-4:
            return 0.5  # no baseline yet: assume ordinary, claim nothing
        return _clamp(self._effort_ema / self.peak_effort, 0.0, 1.0)

    @property
    def conditioning_direction(self) -> str:
        """Which way the climate system is actually moving the room -- for the sensor's
        readout. The engine itself only ever cools, but a user's heat pump may be heating
        on its own, so this reads the measured drift rather than the (cooling-only)
        coefficient: a room trending warmer under active conditioning is being heated.
        """
        if self.confidence <= 0.0 or abs(self.cooling_power) <= 1e-4:
            return "idle"
        return "cooling"

    def cooling_bias(self, cap: float = 0.05) -> float:
        """A small, bounded nudge to the engine's willingness to cool, based on what the
        compressor has actually achieved here -- not on a raw before/after temperature
        comparison, which would credit the AC for the sun going down.

        Deliberately does NOT push down when `struggling`: a room the AC is losing to is a
        room that needs cooling most. Struggling is surfaced as a diagnostic instead.
        """
        if self.confidence <= 0.0:
            return 0.0
        return _clamp((self.effectiveness - 0.5) * 2.0 * cap * self.confidence, -cap, cap)

    @property
    def unexplained_drift(self) -> float:
        """°C/min the room is gaining (or losing) that the model cannot account for.

        The model already explains the outdoors, the sun, the AC and you. Whatever is left
        over, *persistently and in one direction*, is something real that nobody told the
        engine about: a window cracked open, a door left ajar, an oven running, a radiator
        that came on, or a sensor quietly drifting.
        """
        return self._residual_ema if self.confidence > 0.0 else 0.0

    @property
    def anomaly_score(self) -> float:
        """The unexplained drift measured in units of the model's own noise. Above ~2 it is
        no longer plausibly noise. Scaled by confidence, so an unlearned model never accuses."""
        if self.confidence <= 0.0:
            return 0.0
        sigma = max(self._noise_var ** 0.5, 1e-4)
        return _clamp(abs(self._residual_ema) / sigma, 0.0, 10.0) * self.confidence

    def anomaly(self, threshold: float = 2.0) -> str | None:
        """'heating' / 'cooling' when the room is drifting well beyond what the physics
        explains, else None."""
        if self.anomaly_score < threshold:
            return None
        return "heating" if self._residual_ema > 0 else "cooling"

    # ---------- prediction ----------
    def drift(self, indoor: float, outdoor: float, solar: float, cooling: bool = False,
              occupied: bool = False, hour: int | None = None) -> float:
        """Modelled dT/dt (°C per minute) under the given conditions, or 0.0 when the
        inputs aren't there to model with. Pass `hour` (and no measured light) to use the
        sun gain learned for that hour of day instead of the generic sun-height proxy."""
        if indoor is None or outdoor is None:
            return 0.0
        learned = self.learned_sun(hour)
        return (self.leakiness * (outdoor - indoor)
                + (learned if learned is not None else self.solar_gain * solar)
                + (self.cooling_power if cooling else 0.0)
                + (self.occupied_gain if occupied else 0.0)
                + self.internal_gain)

    def predict(self, indoor: float, outdoor, solar: float = 0.0, minutes: float = 30.0,
                cooling: bool = False, step: float = 5.0, occupied: bool = False,
                hour: float | None = None) -> float | None:
        """Indoor temperature `minutes` from now if nothing changes. `outdoor` may be a
        number or a callable(elapsed_minutes) -> °C so a weather forecast can drive it.
        Integrates in short steps, so it curves toward the outdoor temperature the way a
        real room does instead of running away in a straight line."""
        if indoor is None or self.confidence <= 0.0:
            return None
        temperature, elapsed = indoor, 0.0
        while elapsed < minutes:
            span = min(step, minutes - elapsed)
            out = outdoor(elapsed) if callable(outdoor) else outdoor
            if out is None:
                return None
            at = None if hour is None else int(hour + elapsed / 60.0) % 24
            temperature += self.drift(temperature, out, solar, cooling, occupied, at) * span
            elapsed += span
        return temperature

    def anticipation(self, indoor: float, outdoor, solar: float = 0.0, cap: float = 1.5,
                     lookahead: float | None = None, sun_up: bool = True,
                     occupied: bool = False, hour: float | None = None) -> float:
        """How much warmer the room will be over the lookahead if left alone -- the number
        that lets the AC lead a fast-warming room. The lookahead defaults to a fraction of
        the room's own time constant, so a sluggish room is anticipated further ahead than
        a draughty one.

        Trusted model -> a real forecast, scaled by confidence. Not yet trusted -> fall back
        to the context bucket (sun/dark x warmer/cooler), which is useful from day one.
        Nothing learned at all -> 0.0, and the engine simply stays reactive.
        """
        if indoor is None:
            return 0.0
        if lookahead is None:
            tau = self.time_constant
            lookahead = _clamp((tau or 60.0) * 0.25, 10.0, 45.0)
        confidence = self.confidence
        if confidence > 0.0:
            future = self.predict(indoor, outdoor, solar, lookahead, occupied=occupied, hour=hour)
            if future is not None:
                return _clamp(future - indoor, 0.0, cap) * confidence
        # Fallback: what this room has actually done in these conditions before.
        warmer = outdoor is not None and not callable(outdoor) and outdoor > indoor
        key = self.buckets.key(sun_up, bool(warmer))
        if self.buckets.samples(key) >= 5:
            return _clamp(self.buckets.rate(key) * lookahead, 0.0, cap)
        return 0.0


    # ---------- persistence ----------
    def as_dict(self) -> dict:
        """The learned lessons -- coefficients, covariance, counters. About 30 numbers, and
        the whole point of a recursive fit: no sample history is ever stored, so this never
        grows. Persisting it means a restart doesn't throw away days of learning."""
        return {
            "theta": list(self.theta),
            "p": [list(row) for row in self.p],
            "samples": self.samples,
            "rejected": self.rejected,
            "residual_var": self._residual_var,
            "residual_ema": self._residual_ema,
            "noise_var": self._noise_var,
            "peak_effort": self.peak_effort,
            "effort_ema": self._effort_ema,
            "sun_gain": {str(h): g for h, g in self.sun_gain.items()},
            "sun_counts": {str(h): n for h, n in self._sun_counts.items()},
            "unit_offset": self.unit_offset,
            "offset_count": self._offset_count,
            "buckets": {"rates": dict(self.buckets.rates), "counts": dict(self.buckets.counts)},
            "cooling_effect": dict(self.cooling_effect),
        }

    def restore(self, data) -> bool:
        """Reload a persisted fit. Anything malformed or from an older shape is ignored --
        re-learning from scratch is always safe, so a bad restore must never be fatal."""
        if not isinstance(data, dict):
            return False
        try:
            theta = [float(v) for v in data["theta"]]
            p = [[float(v) for v in row] for row in data["p"]]
            if len(theta) != _N or len(p) != _N or any(len(row) != _N for row in p):
                return False  # a model of a different shape (upgrade) -- start clean
            self.theta = theta
            self.p = p
            self.samples = int(data.get("samples", 0))
            self.rejected = int(data.get("rejected", 0))
            self._residual_var = float(data.get("residual_var", 0.0))
            self._residual_ema = float(data.get("residual_ema", 0.0))
            self._noise_var = float(data.get("noise_var", 0.0))
            self.peak_effort = float(data.get("peak_effort", 0.0))
            self._effort_ema = float(data.get("effort_ema", self.peak_effort))
            self.sun_gain = {int(h): float(g) for h, g in (data.get("sun_gain") or {}).items()}
            self._sun_counts = {int(h): int(n) for h, n in (data.get("sun_counts") or {}).items()}
            self.unit_offset = float(data.get("unit_offset", 0.0))
            self._offset_count = int(data.get("offset_count", 0))
            buckets = data.get("buckets") or {}
            self.buckets.rates = {str(k): float(v) for k, v in (buckets.get("rates") or {}).items()}
            self.buckets.counts = {str(k): int(v) for k, v in (buckets.get("counts") or {}).items()}
            self.cooling_effect = {str(k): float(v) for k, v in (data.get("cooling_effect") or {}).items()}
            return True
        except (KeyError, TypeError, ValueError):
            return False
