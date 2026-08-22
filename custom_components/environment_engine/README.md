# Environment Engine

An autonomous climate, air-quality and humidity controller for Home Assistant.

You tell it which sensors and devices a room has. It works out the rest: when to cool, when a fan
is enough, when to shut the blinds, when to seal the flat against outdoor smoke, when to run the
purifier, and when to leave everything alone. It learns the room's thermal behaviour, shifts
cooling toward cheap electricity, and protects your hardware while it does it.

**It never touches heating.** Cooling, air quality and humidity only — so it won't fight your
radiators in winter.

---

## Getting started

1. Add the **Global** entry first (weather, outdoor air quality, electricity price, lightning).
   These are shared by every room, so you set them once.
2. Add a **Room** entry per room. Point it at whatever that room actually has — a climate unit, a
   fan, a purifier, blinds, sensors. **Everything is optional**, and every slot accepts multiple
   entities.
3. Turn on **Auto Apply** when you're ready to let it act. Until then it decides and reports, but
   changes nothing.

The engine only ever uses what exists. A room with nothing but a fan and a thermometer still gets
sensible behaviour.

> After changing anything in the config flow, **fully restart Home Assistant** (not just reload) —
> Home Assistant caches the translations.

---

## What it does

**Cooling that thinks ahead.** It learns how fast your room actually gains and sheds heat, and
starts cooling *before* it needs to when it knows the room warms quickly. Damp air and a hot day
outside both make it cool harder, never less.

**Three modes, one job each.** `cool` whenever the room is above your number. `dry` when the
temperature is already fine but the air is too wet for you -- and only when the coil can actually
condense water, otherwise it would just run the compressor for nothing. `fan_only` when the
compressor *can't* or *needn't* run: quiet hours, an unvented portable unit, the five minutes the
compressor is protected after it stops, a standalone fan that has gone offline, free cooling
through an open window, or drying the coil after a cycle so the unit doesn't start to smell.

**Electricity-aware.** On a spot-price contract it reads the price *forecast* — not just the current
price — ranks the current hour within the day, eases off when power is expensive, and banks coolth
during the genuinely cheapest window ahead of a hot afternoon. On a fixed-price ("fast pris")
contract it ignores price entirely and optimises for comfort.

**Air quality with a sense of proportion.** Purifier speed follows the actual pollution load, and it
knows the difference between fine particles (cooking, smoke) and coarse dust. When outdoor air is
bad it *seals* — closes the ventilation and stops inviting the outside in — and holds that for a
while after the event passes. The purifier is driven by its **own preset modes** (Auto / Silent /
Favorite / Turbo), not as if it were a dumb fan.

**Safety first.** Smoke, an overloaded outlet, or a nearby lightning strike stop everything
immediately, and are held until the danger has genuinely passed.

**Kind to your hardware.** Anti-short-cycling for the compressor, a minimum on/off dwell for the fan
and purifier, and rate limits on every channel so nothing gets flogged.

**Quiet at night.** Optional quiet hours hold the compressor back and move air instead — unless the
room gets genuinely too hot, in which case comfort wins.

---

## Your setpoint is the setpoint

You set a temperature. Above it, the engine cools. That is the whole contract, and nothing except
a safety hold gets to override it -- not the price of electricity, not the time of night, not a
comfort model with an opinion about what you *ought* to find comfortable.

Humidity and outdoor heat are **context**, and context obeys one rule: it may only ever make the
engine cool **harder**, never less. Damp air lowers the setpoint by a degree or two, because muggy
air at 22 C is worse than dry air at 22 C. Nothing raises it.

Everything is in whole degrees, because that is what an air conditioner accepts. A penalty that
doesn't warrant a full degree warrants nothing, and the setpoint is floored rather than rounded --
when the choice is between two integers, the colder one wins.

## What it learns

The engine fits the room's actual physics online (recursive least squares, no dependencies):

    dT/dt = k*(T_out - T_in) + s*solar + c*cooling + b

From that it knows the room's **leakiness** (`k`, and so its thermal time constant), how much the
**sun** heats it, how much the **AC** can actually remove, and its steady **internal gain**. That
makes it *predictive*: "if I do nothing, this room reads 26.4 °C in half an hour."

It stays honest about it:

- Samples are only learned from when the physics is unambiguous — no open window, no mid-interval
  mode change, no restart gaps, no sensor spikes.
- Coefficients are clamped to physically possible ranges, so a bad fit can't produce bad control.
- Confidence scales with evidence and residual noise. Below that bar it falls back to simple
  context-bucketed rates (sun/dark × outdoor warmer/cooler), which work from day one. With nothing
  learned at all, it simply stays reactive.

It also measures **whether cooling actually works** in your room — with the outdoor, solar and
internal loads controlled for — and tells you when the AC is running but *losing* (`Struggling To
Cool`): usually a door left open, a dirty filter, or an undersized unit.

---

## Entities it creates

| Entity | What it tells you |
|---|---|
| **Decision** | What the engine is doing right now, per device, in plain language |
| **Cooling Demand** (%) | How strongly the room wants cooling, and the reasoning behind it |
| **Air Conditioner / Air Purifier Used Today** | Daily runtime (lifetime total drives the filter reminder) |
| **Struggling To Cool** | The AC is running but the room keeps gaining heat |
| **Filter Due** | The purifier has run for its configured filter life |
| **Blocked** | A safety hold is active |
| **Invalid Entities** | A configured entity is missing |
| **Diagnostics** | Engine internals: capabilities, model fit, price rank, lightning |
| **Auto Apply** | Master switch — decide only, or actually act |
| **Exhaust Vented** | For a portable AC without a vent sensor (fails closed, auto-reverts) |

---

## Portable air conditioners

A portable unit dumps condenser heat down its exhaust hose, so running it unvented actively *heats*
the room. Mark it **portable** and cooling is gated on a real vent signal: the contact sensor on the
window the hose goes through, or the manual **Exhaust Vented** switch.

A general door or window sensor will **not** do — an open interior door doesn't vent the hose. When
it can't cool, the unit falls back to fan-only to keep air moving.

---

## Settings that change behaviour most

Every option has inline help in the config flow, so this is not a full list — just the handful
that decide how the engine feels.

| setting | what it does |
|---|---|
| **Target temperature** | The number. Above it, the engine cools. |
| **Humidity sensitivity** | The dew point at which damp air starts costing you a degree or two of setpoint — and at which `dry` runs when the temperature is already fine. Tolerant 17 °C / normal 15 / sensitive 13 / very sensitive 11. |
| **Quiet hours** + **Cool anyway above** | A window where the compressor is held back and the unit fans instead. The "cool anyway" line is a hard user limit: cross it and the compressor runs, full stop. `dry` is still allowed in quiet hours when vented. |
| **Let an empty home drift up to** | How far above target an unoccupied room may get before the engine caps it (default 4 °C, 0 = unlimited). Stops you walking into a 31 °C flat. |
| **Dry the coil after cooling** | Seconds of fan after a cycle to evaporate the wet coil (default 120, 0 = off). This is what stops an AC smelling. |
| **Portable AC** + **Exhaust vent contact** | Marks the unit as portable and tells the engine which contact means the hose is actually vented. Without a vent signal a portable unit will not cool, because it would dump its condenser heat back into the room. |
| **Auto Apply** | Master switch. Off = decide and report, change nothing. |

## Architecture

    snapshot -> evaluators -> planner -> hysteresis -> executors

- **snapshot** — one immutable reading of the world (Celsius, SEK).
- **evaluators** — independent pressures: thermal, solar, humidity, mold, air quality, energy, safety.
- **planner** — safety, then away, then each actuator resolved on its own merits. No actuator is
  privileged; the engine does the most useful thing with whatever devices exist.
- **hysteresis** — rate limits, anti-short-cycling, device wear protection.
- **executors** — idempotent. They read each device's live capabilities and never issue a command a
  device can't honour, or one it's already obeying.

Pure, dependency-free helper modules do the real work and are unit-tested in isolation:
`thermal_model` (the learned physics), `price` (forecast, rank, cheapest window), `psychrometrics`
(dew point, feels-like), `decay` (peak-hold decay for PM recovery, seal and presence holds),
`forecast`, `lightning`, `runtime`, `quiet_hours`, `presets`.

---

## Development

    python -m pytest tests/ -q      # 214 tests
    python -m pyflakes .

`config_flow.py`, `coordinator.py` and the entity platforms are Home Assistant-heavy and aren't
covered by the unit tests, so `AUDIT.md` documents a set of standing static checks for the bug
classes that `pytest` and `pyflakes` structurally cannot see (unresolvable internal imports,
malformed schema tuples, option/field drift, dataclass fields that are written but never read).
Run them before shipping.

See `DESIGN.md` for the reasoning behind each decision and `IMPROVEMENTS.md` for what's next.
