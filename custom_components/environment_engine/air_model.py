"""A learned model of the room's air (pure, no dependencies).

The same idea as `thermal_model`, applied to particulates:

    dPM/dt = -cadr*speed*PM_in - dep*PM_in + inf*PM_out + gen

  cadr -- how fast the purifier actually cleans, per unit of fan speed. This is the number
          a filter reminder should really be based on.
  dep  -- natural loss: particles settle out and leak away on their own.
  inf  -- how fast outdoor air gets in. The flat's leakiness to smoke and pollen.
  gen  -- the baseline indoor source (cooking, candles, dust, you).

Fitted online with recursive least squares, so it stores lessons, never samples.

Why it matters: filter life is normally an *hours* counter, which is a guess. Here the
purifier's cleaning rate is **measured**, so a clogging filter shows up as `cadr` falling
away from its best -- "this filter has lost 40% of its power" rather than "it has been on
for 500 hours". The learned `inf` also tells the seal logic how quickly bad outdoor air
will actually reach you.
"""
from __future__ import annotations

_N = 4                     # cadr, dep, inf, gen
_FORGET = 0.997
_MAX_DT = 30.0             # minutes
_WARMUP = 30               # PM is noisier than temperature: demand more evidence
_TRUSTED = 120

_CADR_RANGE = (0.0, 1.0)   # per minute, at full speed
_DEP_RANGE = (0.0, 0.5)
_INF_RANGE = (0.0, 0.5)
_GEN_RANGE = (0.0, 20.0)   # ug/m3 per minute

_SPEED_FRACTION = {None: 0.0, "off": 0.0, "low": 0.33, "medium": 0.66, "high": 1.0}


def _clamp(value, low, high):
    return max(low, min(value, high))


def speed_fraction(action, speed) -> float:
    """The purifier's airflow as a 0..1 fraction, from the engine's own action/speed."""
    if action in (None, "off", "none"):
        return 0.0
    return _SPEED_FRACTION.get(speed, 0.66)


class AirModel:
    def __init__(self) -> None:
        self.theta = [0.0] * _N
        self.p = [[100.0 if i == j else 0.0 for j in range(_N)] for i in range(_N)]
        self.samples = 0
        self.rejected = 0
        self._residual_var = 0.0
        self.peak_cadr = 0.0       # the best this purifier has ever managed (a fresh filter)

    # ---------- fitting ----------
    def update(self, previous, current, dt_minutes: float, speed: float) -> bool:
        if not self._clean(previous, current, dt_minutes):
            self.rejected += 1
            return False
        pm_in = previous.pm25 if previous.pm25 is not None else previous.pm10
        # The outdoor reading may be an AQI rather than ug/m3. That's fine: `inf` is fitted,
        # so it simply absorbs the scale factor -- what matters is that the two move together.
        pm_out = previous.outdoor_aqi if previous.outdoor_aqi is not None else 0.0
        pm_now = current.pm25 if current.pm25 is not None else current.pm10
        rate = (pm_now - pm_in) / dt_minutes
        x = [-speed * pm_in, -pm_in, pm_out, 1.0]
        self._rls(x, rate)
        self.samples += 1
        # A fresh filter defines "full power". Only trust that once the fit has settled.
        if self.confidence > 0.5:
            self.peak_cadr = max(self.peak_cadr, self.clean_rate)
        return True

    def _clean(self, previous, current, dt_minutes: float) -> bool:
        if previous is None or current is None:
            return False
        if not (0.0 < dt_minutes <= _MAX_DT):
            return False
        before = previous.pm25 if previous.pm25 is not None else previous.pm10
        after = current.pm25 if current.pm25 is not None else current.pm10
        if before is None or after is None or before < 0 or after < 0:
            return False
        if previous.window_open or current.window_open:
            return False               # an open window is not a sealed room
        if abs(after - before) > 200:
            return False               # sensor glitch, not air
        return True

    def _rls(self, x, y) -> None:
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

    # ---------- what it learned ----------
    @property
    def clean_rate(self) -> float:
        """Measured CADR: the fraction of the room's particulates the purifier removes per
        minute at full speed."""
        return _clamp(self.theta[0], *_CADR_RANGE)

    @property
    def deposition(self) -> float:
        return _clamp(self.theta[1], *_DEP_RANGE)

    @property
    def infiltration(self) -> float:
        """How readily outdoor air gets in -- the flat's leakiness to smoke and pollen."""
        return _clamp(self.theta[2], *_INF_RANGE)

    @property
    def generation(self) -> float:
        return _clamp(self.theta[3], *_GEN_RANGE)

    @property
    def confidence(self) -> float:
        if self.samples < _WARMUP:
            return 0.0
        coverage = min((self.samples - _WARMUP) / (_TRUSTED - _WARMUP), 1.0)
        noise = 1.0 / (1.0 + 0.5 * self._residual_var)
        return _clamp(coverage * noise, 0.0, 1.0)

    @property
    def filter_health(self) -> float | None:
        """0..1 -- how much of its best cleaning power the purifier still has. This is a
        *measurement*, not an hours estimate: a clogged filter simply stops removing
        particulates, and that shows up here."""
        if self.confidence <= 0.5 or self.peak_cadr <= 0.01:
            return None                # not enough evidence to accuse anyone's filter
        return _clamp(self.clean_rate / self.peak_cadr, 0.0, 1.0)

    def minutes_to_clear(self, pm_in: float, target: float, speed: float = 1.0) -> float | None:
        """How long the purifier needs to bring the room down to `target`, at this speed."""
        if pm_in is None or pm_in <= target or self.confidence <= 0.0:
            return None
        decay = self.clean_rate * speed + self.deposition
        if decay <= 1e-4:
            return None                # it isn't actually clearing the room
        import math
        return min(math.log(pm_in / max(target, 1e-3)) / decay, 600.0)

    # ---------- persistence ----------
    def as_dict(self) -> dict:
        return {
            "theta": list(self.theta),
            "p": [list(row) for row in self.p],
            "samples": self.samples,
            "rejected": self.rejected,
            "residual_var": self._residual_var,
            "peak_cadr": self.peak_cadr,
        }

    def restore(self, data) -> bool:
        if not isinstance(data, dict):
            return False
        try:
            theta = [float(v) for v in data["theta"]]
            p = [[float(v) for v in row] for row in data["p"]]
            if len(theta) != _N or len(p) != _N or any(len(row) != _N for row in p):
                return False
            self.theta, self.p = theta, p
            self.samples = int(data.get("samples", 0))
            self.rejected = int(data.get("rejected", 0))
            self._residual_var = float(data.get("residual_var", 0.0))
            self.peak_cadr = float(data.get("peak_cadr", 0.0))
            return True
        except (KeyError, TypeError, ValueError):
            return False
