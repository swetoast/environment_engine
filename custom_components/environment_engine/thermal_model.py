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

The four coefficients are fitted online with recursive least squares (a forgetting
factor keeps it adapting as seasons and furniture change). That makes the model
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
_WARMUP = 20               # clean samples before the model is trusted at all
_TRUSTED = 60              # clean samples for full confidence

# Physically sane bounds -- a bad fit must never produce nonsense control.
_K_RANGE = (0.0, 0.05)     # per minute, per °C of indoor/outdoor difference
_C_RANGE = (-0.5, 0.0)     # cooling can only cool
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

    # ---------- fitting ----------
    def update(self, previous, current, dt_minutes: float, cooling: bool, solar: float) -> bool:
        """Feed one interval. Returns True if it was a clean, usable sample.

        `previous`/`current` are snapshots. A sample is only used when the physics is
        unambiguous: no window open, no mid-interval mode change, sane timing and readings.
        """
        if not self._clean(previous, current, dt_minutes):
            self.rejected += 1
            return False
        indoor, outdoor = previous.indoor_temp, previous.outdoor_temp
        rate = (current.indoor_temp - indoor) / dt_minutes           # °C per minute
        occupied = 1.0 if getattr(previous, "occupancy", False) else 0.0
        x = [outdoor - indoor, solar, 1.0 if cooling else 0.0, occupied, 1.0]
        self._rls(x, rate)
        self.samples += 1
        # Context bucket (works from day one, and is the fallback while the model warms up).
        self.buckets.update(self.buckets.key(bool(previous.sun_up), outdoor > indoor), rate)
        if cooling:
            self._record_cooling(rate, outdoor)
        return True

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
        if previous.hvac_mode != current.hvac_mode:
            return False                                   # mode flipped mid-interval
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
        """0..1 -- how well cooling actually works in this room, measured with the
        outdoor/solar/internal load controlled for. A healthy split unit removes on the
        order of 0.08 °C per minute; much less than that and the compressor is buying
        little for its energy."""
        if self.confidence <= 0.0:
            return 0.5  # unknown: assume ordinary, bias nothing
        return _clamp(-self.cooling_power / 0.08, 0.0, 1.0)

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

    # ---------- prediction ----------
    def drift(self, indoor: float, outdoor: float, solar: float, cooling: bool = False,
              occupied: bool = False) -> float:
        """Modelled dT/dt (°C per minute) under the given conditions, or 0.0 when the
        inputs aren't there to model with."""
        if indoor is None or outdoor is None:
            return 0.0
        return (self.leakiness * (outdoor - indoor)
                + self.solar_gain * solar
                + (self.cooling_power if cooling else 0.0)
                + (self.occupied_gain if occupied else 0.0)
                + self.internal_gain)

    def predict(self, indoor: float, outdoor, solar: float = 0.0, minutes: float = 30.0,
                cooling: bool = False, step: float = 5.0, occupied: bool = False) -> float | None:
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
            temperature += self.drift(temperature, out, solar, cooling, occupied) * span
            elapsed += span
        return temperature

    def anticipation(self, indoor: float, outdoor, solar: float = 0.0, cap: float = 1.5,
                     lookahead: float | None = None, sun_up: bool = True,
                     occupied: bool = False) -> float:
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
            future = self.predict(indoor, outdoor, solar, lookahead, occupied=occupied)
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
            buckets = data.get("buckets") or {}
            self.buckets.rates = {str(k): float(v) for k, v in (buckets.get("rates") or {}).items()}
            self.buckets.counts = {str(k): int(v) for k, v in (buckets.get("counts") or {}).items()}
            self.cooling_effect = {str(k): float(v) for k, v in (data.get("cooling_effect") or {}).items()}
            return True
        except (KeyError, TypeError, ValueError):
            return False
