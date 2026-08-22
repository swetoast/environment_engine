# Environment Engine — Design

Capability-aware decision engine:
**snapshot → evaluators (incl. effective-target resolution) → planner → hysteresis → executors.**

## Temperature controls; comfort is context

Your setpoint is the target. Not a suggestion, not a starting point for a model to improve on.

Psychrometrics and thermal comfort are **context**, and context obeys one rule: **it may only
ever make the engine cool harder, never less.** Damp air lowers the setpoint. Heat outside lowers
it. Nothing raises it, and nothing gets to decide a warm room is fine.

    indoor > your setpoint  ->  COOL.  Only safety outranks this.

The unit takes whole degrees, so every term is a whole degree. A penalty that doesn't warrant a
full degree warrants nothing -- and the setpoint is floored, never rounded, so when the choice is
between two integers the colder one wins.

Mode selection is four lines:

    above setpoint, can cool     -> COOL at the driven setpoint
    above setpoint, blocked      -> FAN_ONLY   (unvented portable, or quiet hours)
    at setpoint, air too wet     -> DRY        (allowed in quiet hours when vented)
    otherwise                    -> OFF

DRY needs the dew point above both your sensitivity limit and the coil (~12 C) -- below that
there is nothing to condense and it would just run the compressor for nothing.

## Global vs room configuration

Setup is split into two entry types. A single **Global** entry holds the sensors shared by the
whole home -- weather/outdoor temperature, outdoor air quality (AQI or PM), lightning, forecast, energy price,
and the daily average -- configured once. Each **Room** entry holds that room's own devices and sensors plus
its comfort options. A room's coordinator merges the global config underneath its own (room wins
on conflict) and re-reads it every cycle, so changing a global sensor updates every room. The
global entry is config-only (no coordinator or entities); room entities are named
`<domain>.<room>_environment_engine_<function>`.

## Portable AC (vent gating)

A portable AC dumps condenser heat through an exhaust hose, so running cool/dry when the hose
isn't vented just net-heats the room. Mark the unit **portable** and cooling is gated on a vent
signal — the window/vent sensor being open, or a manual **Exhaust Vented** switch that fails
closed and auto-reverts after a timeout. When it can't cool, the AC's own **fan_only** still
circulates (unless a standalone fan exists, which is preferred to avoid double-fanning). Passive
cooling is suppressed for portable units, since that window *is* the exhaust vent.

## Feels-like temperature

Humid air feels warmer, so the quiet-hours "cool anyway above" line is compared against a
**feels-like** temperature (`psychrometrics.feels_like`): a bounded heat-index bump above ~20 °C
that grows with warmth and humidity, capped by the per-room knob.

**Known overlap, flagged rather than hidden.** The dew-point humidity penalty in the target
resolver does a similar job by a better method, and the two disagree — the heat index adds about
+0.1 °C where PMV reads +1.5 at 30 °C. Two comfort metrics is one too many; retiring one of them is
an open item in `IMPROVEMENTS.md`. Until then `feels_like` is confined to the quiet-hours
comparison and the humidity penalty owns the setpoint.


## Pricing mode (spot vs fixed)

A global **pricing mode** picks the electricity strategy. **Spot** (default) runs the full
time-of-use logic below. **Fixed** (flat-rate "fast pris") disables all of it: the energy penalty
is zero, nothing is ever "expensive", and pre-cooling banks coolth freely ahead of heat for
comfort — there are no cheap/expensive hours to shift against. Set once on the Global entry.

## Price forecast (rank + load-shifting)

The engine now reads the spot-price *forecast* via `price.py` (a dedicated forecast sensor slot;
falls back to the price sensor's own attributes). It parses Elpriset's today/tomorrow/forecast
{time_start, SEK_per_kWh} slots, Nordpool's raw_today/raw_tomorrow, and plain hourly floats, at any
slot granularity (15-min, hourly). Two signals
come from it: a smooth **rank** (the current price's percentile within the day, so eco easing ramps
in proportionally instead of flipping around the average), and a **cheapest-window** flag that fires
only when now is the cheapest upcoming block *and* the price is below the day's median (so it never
pre-cools during the least-bad hour of an expensive evening) — so forecast pre-cooling banks coolth in the cheapest
hours ahead of a heat load rather than merely "when it's cheap now". Falls back to the daily-average
comparison when no forecast is published.

## Sensors (what the user sees)

- **Decision** -- what the engine is doing right now, in plain language, per device.
- **Cooling Demand (%)** -- how strongly the room wants cooling, with the reasoning behind it
  (target, feels-like, how fast the room warms/cools per hour, incoming heat from the forecast).
- **Air Conditioner / Air Purifier Used Today (h)** -- daily usage, rolling over at local midnight.
  The lifetime total rides along as an attribute and drives the filter-life reminder.
- **Diagnostics** (diagnostic category) -- engine internals: capabilities, learning counters,
  price rank, lightning detail, invalid entities.

## Portable AC: the exhaust vent is its own sensor

`vented` comes ONLY from the dedicated **exhaust vent contact** (the window the hose goes through)
or the manual **Exhaust Vented** switch. A general door/window contact must never imply the hose is
vented -- otherwise opening an interior door would let a portable unit cool into a sealed room,
dumping its condenser heat straight back inside.

## Quiet hours

An optional nightly window (it may wrap midnight) where the **compressor is held back** and the
engine moves air instead: the AC's own `fan_only`, plus any standalone fan. This is the one case
where the AC is allowed to fan alongside a standalone fan -- using its fan_only is the whole point.
It is not a hard block: if the room's feels-like temperature reaches **"cool anyway above"**,
comfort wins and it cools regardless, so quiet hours can never let the room cook.

Note this is also why `fan_only` is otherwise rare: outside quiet hours the AC defers to a
standalone fan (no double-fanning), so a room with its own fan never sees the AC fan. `dry` is
likewise rare by design -- it only wins when the drying need actually outweighs the heat need.

## The purifier is a purifier, not a fan

Even when the entity lives in the `fan` domain (`fan.air_purifier`), a purifier is driven by its
**own preset modes** -- Auto / Silent / Favorite / Turbo -- resolved from the device's reported
`preset_modes` (`presets.py`). A raw percentage is only the fallback for devices with no presets.
The purifier never runs for air *circulation*: it answers to the air-quality signal alone, while
the fan handles heat and circulation.

The **ionizer** has its own mode: *with the purifier* (default), *only on heavy pollution*, or
*never*. Previously it was hard-gated on a pressure surge that the reduced air-quality sensitivity
made effectively unreachable, so it never ran.

## Learned thermal model (thermal_model.py)

Rather than a single "it warms at X °C/min" number, the engine fits the room's actual physics
online with recursive least squares:

    dT/dt = k*(T_out - T_in) + s*solar + c*cooling + o*occupied + b

learning the envelope **leakiness** k (and from it the room's time constant tau), the **solar gain**
s, the AC's **effective cooling power** c, and the steady **internal gain** b. Against a simulated
room it recovers the true coefficients to within a few percent and predicts 30 minutes ahead to
~0.0 °C.

This makes anticipation a real *forecast* ("if I do nothing, 26.4 °C in half an hour") instead of a
straight-line extrapolation, and the lookahead is derived from the room's own tau -- a sluggish room
is led further ahead than a draughty one.

**It stays honest.** Samples are only learned from when the physics is unambiguous (no open window,
no mid-interval mode change, sane timing and readings); coefficients are clamped to physically
possible ranges; and `confidence` scales with evidence and residual noise. Below that bar the engine
falls back to **bucketed rates** (sun/dark x outdoor warmer/cooler), which are useful from day one,
and with nothing learned at all it simply stays reactive.

It also tracks **cooling effectiveness** (°C actually removed per minute, by outdoor temperature
band) and flags `struggling` when the compressor runs but the room still gains heat -- an undersized
unit, a dirty filter, or a door left open.

## Learning whether cooling actually works

The engine used to judge cooling by a raw before/after temperature comparison, and it counted fan
*circulation* as a cooling attempt. Both were wrong: a fan doesn't lower air temperature, so every
circulation cycle on a hot day logged a "cooling failure" and biased the engine **against** cooling;
and even for real cooling the measure was confounded -- it credited the AC when the sun set and
blamed it when the outdoors heated up.

Cooling effectiveness now comes from `ThermalModel`, which isolates the compressor's contribution
with the outdoor, solar and internal loads controlled for. `cooling_bias` is a small bounded nudge
(±0.05, scaled by model confidence): lean into cooling in a room where it demonstrably works, ease
off where the compressor buys almost nothing. It deliberately does **not** back off when the room is
`struggling` -- a room the AC is losing to is the room that needs cooling most; that is surfaced as
the **Struggling To Cool** problem sensor instead (open door, dirty filter, undersized unit).

`AdaptiveLearning` now tracks **drying** only, where a simple before/after humidity check is fair.

## Sampling, memory and persistence

The model takes one sample per coordinator refresh (default **60 s**). It never stores those
samples: a recursive fit keeps only the **lessons** -- five coefficients and a 5x5 covariance
matrix, about 30 numbers, constant forever. Old evidence fades on its own through a forgetting
factor, so it tracks a new curtain, a clogging filter or a change of season without being told.

The fit is **persisted** (~1 kB) and reloaded on startup, so a restart no longer throws away days
of learning. A corrupt or older-shape store is ignored rather than fatal -- re-learning is always
safe.

It keeps learning **while you are away**: an empty house is the cleanest laboratory there is, with
no doors, no cooking and no bodies. But an occupied room and an empty one are genuinely different
thermal systems, so "someone is home" is a **coefficient of the model** (`o`), not a reason to stop
sampling. Fitting a single blurred internal gain across both states was wrong in both; separating
them changes the one-hour prediction by well over a degree.

## Learned air model (air_model.py)

The same recursive fit, applied to particulates:

    dPM/dt = -cadr*speed*PM_in - dep*PM_in + inf*PM_out + gen

so the engine **measures** what the purifier actually achieves (`cadr`), how readily outdoor air
gets in (`inf` -- the flat's leakiness to smoke and pollen), the natural settling rate, and the
baseline indoor source.

The payoff is the filter reminder. An hours counter is a guess; a clogged filter simply stops
removing particulates, and that shows up directly as `cadr` falling away from the best this unit
has ever managed. **Filter Due** now fires on measured degradation (below half its original power)
as well as on hours, and reports `filter_health_pct`.

## Unexplained heat

The thermal model already accounts for the outdoors, the sun, the AC and you. A persistent,
one-sided residual is therefore something real that nobody told the engine about: a window cracked
open, a door left ajar, an oven running, a radiator that came back on, or a temperature sensor
drifting out of calibration. The **Unexplained Heat** sensor reports it, in °C/hour.

The yardstick is the room's *quiet-time* noise, updated only from ordinary-looking errors. Folding
the anomaly into the same variance it is measured against would let a big enough event hide inside
its own inflated error bars -- which is exactly what happened in the first cut.


## When FAN_ONLY earns its place

`fan_only` is what the unit does when the compressor **cannot** or **need not** run. It is never
chosen over cooling -- a fan moves heat around, it does not remove any. Six cases:

    quiet hours, below your cool-anyway line   compressor held back, air still moves
    portable AC with no vent                   cooling would dump condenser heat indoors
    anti-short-cycle timer running             up to 5 min protected; move air meanwhile
    standalone fan configured but offline      an unavailable fan is not an air mover
    free cooling through an open window        outside is doing the work
    mould risk with the room at target         airflow discourages damp corners
    just after cooling or drying stopped       evaporate the water left on the coil

The third and fourth were gaps. The compressor is protected for five minutes after it stops, and
the unit used to sit completely idle for that whole time with the room above target -- now it
fans, which costs almost nothing and destratifies the ceiling heat so the next cycle starts from
an honest reading. And a standalone fan that is configured but unavailable used to still make the
AC defer to it, leaving the room still while both devices did nothing.

**Coil dry-out.** A coil that has just been condensing water is wet, and a wet coil sitting in a
dark box is how an air conditioner starts to smell. After cooling or drying stops the blower runs
on for a couple of minutes to evaporate it -- the same thing the manufacturers' own "auto clean"
does. A safety block still stops it dead, and a room that warms mid-cycle still respects the
compressor timer.

Substituting fan_only never sneaks the compressor past its own timer; that is asserted separately.

## Core principle: capability-aware, nothing privileged

Every entity slot is optional. The engine reads only what is configured and does the most
useful thing with whatever devices exist — a lone fan, a lone purifier, an AC, or any mix.
Each actuator is resolved **independently** from the same environmental *pressures* and gated
only on its own capability; no actuator is primary. Multiple concerns run at once (cool while
shading while purifying); the `strategy` label is only a human-facing summary of the dominant
driver.

The engine is a **cooling / air-quality / humidity** controller. It only manages the HVAC
modes `cool`, `dry`, and `fan_only`, and deliberately never touches `heat`, so it will not
fight a heating setup in winter.

## Pipeline stages

1. **snapshot** (`snapshot.py`, built in `coordinator.py`) — a frozen, keyword-only reading of
   just the configured entities. All temperatures are normalized to Celsius on read
   (`units.py`); actuator capabilities are decoded from each device's live
   `supported_features` bitmask (`features.py`).
2. **evaluators** (`evaluators/`) — turn raw readings into neutral, `None`-guarded *pressures*:
   safety, solar, energy, thermal, humidity, mold, air quality. A missing sensor contributes
   zero. No evaluator commands a device. The **effective climate target** is resolved here
   (`target_resolver.py`) and fed into the thermal evaluator and the climate resolver.
3. **planner** (`planner.py`) — safety → away → five independent resolvers (`resolvers/`) →
   one `Decision`.
4. **hysteresis** (`hysteresis.py`) — per-channel rate limiting so no device flaps.
5. **executors** (`executors/`) — apply each channel to its device, **idempotently**.

## One comfort target; the engine derives comfort / eco / sleep itself

There are no modes to pick — just a single configured **comfort temperature**. The target
resolver moves the *effective* setpoint within safe bounds from live conditions:

- **lower** (cool harder): indoor heat excess (saturating), a warming trend, hot outdoors
  (small preemptive term), forecast pre-cooling when a hot period is coming *and* power is
  currently cheap, and a warm-and-humid comfort drop.
- **raise** (ease off): night (sleep-like), expensive energy (eco — see below), and an open window with
  cooler air outside (let passive ventilation work).

"Away" needs no target term — the planner idles an empty room. Everything is anchored to the
stable baseline (never to the current room temperature, so there is no runaway), clamped to a
maximum correction and to the device's min/max, and rounded to whole degrees as a deadband.

## Air quality

Prefers a configured aggregate **AQI** sensor (its `dominant_factor` explains the reason);
falls back to raw CO₂/VOC when no AQI sensor is set. The purifier's run state comes from the
AQI crossing a configurable threshold, its **speed** scales with the magnitude (low/medium/
high), and the **ionizer** is an independent auxiliary that engages only on a strong surge.
The engine *consumes* the AQI value — it does not recompute air quality.

## Humidity

A humidity/mold pressure drives the AC's **dry** mode or a **dehumidifier** (a dedicated
dehumidifier frees the AC to cool instead). Additionally, when the room is **warm**, high
humidity applies a bounded extra cooling-setpoint drop (configurable comfort level + strength;
0 disables). A cool-but-humid room is left to dry mode / the dehumidifier.

## Energy pricing

Prefers a **relative** model: point the optional average/reference slot at a daily-average price
sensor and "expensive" means *above today's average*, so it self-tunes across seasons and price
regimes (penalty scales with how far above average; the cheap slots invite pre-cooling). Without
an average sensor it falls back to a fixed SEK threshold. All the common Swedish spot sources
(Nord Pool, Elpriset, Vattenfall) expose both a current price and a daily average and work as-is.

## Forecast pre-cooling

Precool is driven by a **weighted heat outlook** (`heat_outlook`) rather than a single forecast
peak: it weights how hot, how soon, and how sustained the upcoming heat is, so a sustained hot
afternoon banks coolth while a lone distant spike doesn't — and only when power is cheap now.

## Runtime & maintenance

A `RuntimeTracker` accumulates AC and purifier on-time; two diagnostic sensors expose the hours
(persisted across restarts), and a **Filter Due** binary sensor trips once the purifier passes a
configurable filter-life. Attribution is per-interval to whatever ran during it.

## Forecast

The forecast slot accepts a weather entity or a forecast sensor; the engine parses its
`forecast` attribute (`forecast.py`) to find the peak temperature over the next few hours. A
plain numeric sensor that already reports a peak also works.

## Fan behaviour

The fan resolves independently and can run alone: on cooling demand (also boosting an actively
cooling AC via the shared trigger), to assist air cleaning whenever air quality is elevated
enough to run the purifier, for mould airflow, for passive ventilation, or as a gentle comfort
breeze when it's warm but not yet cool-worthy (opt-out).

## Fresh-air ventilation (CO2)

A purifier filters particles but can't remove CO2. An optional fresh-air actuator (fan, ERV,
vent, or window opener) runs when CO2 is high to actually ventilate, with a deadband to avoid
flapping. It's suppressed during a seal event and off when away.

## Circadian sleep (lux)

When the room is genuinely dark (lux at/below the sleep threshold) and the sun is down, the
engine treats it as sleep: it eases the setpoint more than a plain night and keeps the fan and
purifier quiet -- unless an outdoor air-quality event needs full airflow. Without a lux sensor,
behaviour falls back to the sun-only night easing.

## Particle size & source intelligence

Optional indoor PM1/PM2.5/PM10 sensors let the engine do what a single AQI number can't:
* **Size** — one indoor *fine* slot (PM1/PM2.5: smoke, cooking) drives hard purification; an
  optional indoor *coarse* slot (PM10: dust, pollen) is weighted lower for a gentler response.
  Outdoor particulate belongs in the Global outdoor slot, not the indoor coarse slot.
* **Source** — a high *indoor* particle level with clean *outdoor* air is an **indoor event**
  (cooking, candle): purify hard **and air out** (opening up helps). High *outdoor* air is an
  infiltration event: **seal** and purify, don't ventilate. So cooking and wildfire smoke can
  produce identical indoor readings yet opposite ventilation decisions.

## Air-quality recovery (post-event decay)

An air-quality spike (cooking, smoke) keeps the purifier elevated through its **decay tail**
rather than dropping the instant the reading dips. A peak-hold (`PeakDecay`) holds the pressure
near its recent peak and decays it toward the live reading over a configurable half-life, so the
room finishes clearing before the purifier steps down. 0 disables (react to the live reading).

## Seal & purify (outdoor air-quality events)

An optional outdoor AQI/PM2.5 sensor drives a seal response: above the seal threshold (wildfire
smoke, heavy pollen) the engine stops treating an open window as free cooling, drops the
ventilation setpoint relaxation, and runs the purifier hard (high + ionizer) preemptively --
outdoor air will infiltrate, so filter rather than invite it in.

## Condensation guard

The engine will not chase a setpoint far below the room's dew point, where surfaces start to sweat.

**Bounded by your setpoint.** The guard may lower how deep the engine cools; it may never raise the
setpoint above the number you asked for. An earlier unbounded version did exactly that: on a hot
humid day the dew point sat above the target and the guard pushed the setpoint to the device
maximum, so the room got neither cooling nor drying at precisely the moment it needed both. Cooling
toward your setpoint is always allowed -- the coil condenses water on the way down and the dew point
falls with it.


## Compressor protection

An anti-short-cycle guard keeps the AC compressor from switching on or off more often than a
configurable minimum cycle time (default 5 min), protecting the hardware. It sits in the
hysteresis stage and treats only cool/dry as compressor-active (fan_only/off are not).

## Safety

Smoke and outlet-overload holds are binary. Lightning is a **dynamic hold** driven by Blitzortung `geo_location.lightning_strike_*` strikes.
It's gated by config: the user points at a Blitzortung sensor in the Global setup to confirm the
integration is installed, and only then does the engine scan the per-strike entities. A max
reaction distance bounds it. The hold window
and reaction radius scale with storm intensity (strike count) and proximity, and it auto-releases
as strikes age out — so a lone distant strike fades in seconds while a close, active storm holds
for up to ~30 min. Lightning lives on the Global entry.


Overrides everything: smoke, lightning, or outlet-overload stops active devices and blocks
auto-apply for that cycle.

## Multiple devices per slot

Every slot accepts **several entities** (a room can have two fans, three temperature sensors,
several window contacts). Sensor readings are aggregated into the snapshot — temperatures and
humidity by **mean**, CO₂/VOC/AQI by **worst-case (max)**, lux by **brightest (max)**, price by
mean; window/smoke/lightning/overload are **any**, and presence is occupied if **any** source
is home. Climate capability is the **safe common denominator** across units (intersection of
supported modes, highest min / lowest max, feature flags true only if all support them).
Actuator commands **fan out to every device** in the slot, each checked against its own live
state so a device is only commanded when it isn't already correct. Separate rooms are still
separate config-entry instances; multiple-per-slot is for several devices *within one zone*.

## Verification-first workflow

`py_compile` + `pyflakes` + `pytest` before every change (80 tests). The full source is
concatenated into `ALL_CODE.md`; diagrams live in `FLOWCHARTS.md`.
