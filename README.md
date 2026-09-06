# Environment Engine

[![hacs][hacs-badge]][hacs-url]
[![release][release-badge]][release-url]

An autonomous climate, air-quality and humidity controller for Home Assistant.

You point it at whatever sensors and devices a room already has. It decides when to cool, when a
fan is enough, when to dehumidify, when to shut the blinds, when to seal the flat against outdoor
smoke, when to run the purifier — and when to leave everything alone.

**It never heats.** Cooling, air quality and humidity only, so it will not fight your radiators in
winter.

## Highlights

- **Your setpoint is the setpoint.** Above it, the engine cools. Only a safety hold overrides that
  — not price, not the time of night, not a comfort model.
- **Learns your room.** Fits the actual thermal physics online — envelope leakiness, solar gain, how
  much your AC really removes, the heat you add by being home — and cools *ahead* of the heat.
- **Electricity-aware.** Reads the spot-price forecast and banks cooling while power is cheap.
  Never lets price stop it cooling.
- **Safety first.** Smoke, an overloaded outlet, or nearby lightning stop everything immediately.
- **Works with what you have.** Every sensor and device slot is optional. A room with one fan and a
  thermometer still gets sensible behaviour.

## Requirements

- Home Assistant 2024.6 or newer
- At least one climate, fan or purifier entity to control
- No external dependencies, no cloud, no API keys

## Installation

### HACS

1. In HACS, go to **Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/swetoast/environment_engine` as an **Integration**.
3. Search for **Environment Engine**, install it, and restart Home Assistant.

### Manual

1. Copy `custom_components/environment_engine` into your Home Assistant
   `config/custom_components` directory.
2. Restart Home Assistant.

## Configuration

Everything is configured in the UI — **Settings → Devices & Services → Add Integration →
Environment Engine**. Nothing goes in `configuration.yaml`.

There are two kinds of entry.

### Global entry — add this once

Shared outdoor data, so you set it once rather than repeating it per room. Every field is optional.

| Field | Used for |
|---|---|
| Weather (outdoor) | Outdoor temperature and the forecast |
| Forecast source | Forecast highs, for pre-cooling before a hot afternoon |
| Outdoor air quality (AQI or PM) | Sealing the home during a smoke event |
| Energy price | Shifting cooling toward cheap power |
| Average / reference price | Deciding what counts as expensive |
| Price forecast | Finding the cheapest upcoming window |
| Lightning sensor (Blitzortung) | Stopping everything during a storm |

### Room entry — add one per room

Point it at what the room actually has. **Every slot is optional and every slot accepts multiple
entities.**

| Section | Slots |
|---|---|
| **Climate & comfort** | air conditioner / heat pump, indoor temperature, fan, blinds, light level |
| **Air quality** | AQI, PM1, PM2.5, PM10, purifier, purifier ionizer, ventilation, CO₂, VOC |
| **Humidity** | indoor humidity, humidifier / dehumidifier |
| **Presence & safety** | occupancy, window/door contact, smoke alarm, outlet overload, exhaust vent contact |

Leave **Auto Apply** off at first. The engine will decide and report without touching anything,
which is a good way to watch what it *would* do before letting it act.

> After changing anything in the config flow, **fully restart Home Assistant** — a reload is not
> enough, because Home Assistant caches integration translations.

## Options

Every option has inline help in the config flow. These are the ones that most change how it feels.

| Option | Default | What it does |
|---|---|---|
| Target temperature | 22 °C | The number. Above it, the engine cools. |
| Humidity sensitivity | Normal | The dew point at which damp air starts costing you a degree of setpoint, and at which dehumidifying kicks in. Tolerant 17 °C · Normal 15 · Sensitive 13 · Very sensitive 11. |
| Quiet hours | Off | A nightly window where the compressor is held back and the unit fans instead. |
| Cool anyway above | 26 °C | Hard limit during quiet hours. Cross it and the compressor runs, full stop. |
| Let an empty home drift up to | 4 °C | How far above target an unoccupied room may get before the engine caps it, so you do not walk into a 31 °C flat. `0` lets it drift freely. |
| Dry the coil after cooling | 120 s | Runs the fan briefly after a cycle to evaporate the wet coil. This is what stops an air conditioner smelling. `0` disables. |
| Lightning reaction radius | 40 km | Any strike inside this stops the compressor. Closer and busier storms hold longer. |
| Portable AC | Off | Gates cooling on a real vent signal — see below. |
| Auto Apply | Off | Master switch: decide only, or actually act. |

## Entities

Each room entry creates:

| Entity | Type | Tells you |
|---|---|---|
| Decision | Sensor | What the engine is doing right now, per device, in plain language |
| Cooling Demand | Sensor (%) | How strongly the room wants cooling, and the reasoning behind it |
| Air Conditioner Used Today | Sensor (h) | Daily runtime |
| Air Purifier Used Today | Sensor (h) | Daily runtime; the lifetime total drives the filter reminder |
| Struggling To Cool | Binary sensor | The AC is running but the room keeps gaining heat |
| Unexplained Heat | Binary sensor | The room is warming in a way the learned model cannot account for |
| Filter Due | Binary sensor | Measured filter degradation, or configured hours |
| Blocked | Binary sensor | A safety hold is active |
| Invalid Entities | Binary sensor | A configured entity is missing or unavailable |
| Diagnostics | Sensor | Engine internals: capabilities, model fit, price rank, lightning |
| Auto Apply | Switch | Decide only, or act |
| Exhaust Vented | Switch | Manual vent signal for a portable AC |
| Apply Decision | Button | Act on the current decision now |
| Refresh Decision | Button | Re-evaluate without waiting for the next update |
| Reset Learning | Button | Forget everything learned about this room |

## How it decides

One rule matters more than the rest: **above your setpoint means cool.** Humidity and outdoor heat
are context, and context may only ever make it cool *harder* — never less, and never "the room is
fine actually".

```
safety blocked (smoke / lightning / outlet)   →  everything off
above your setpoint, compressor available     →  cool
above your setpoint, compressor blocked       →  fan only
at setpoint but the air is too damp           →  dry
otherwise                                     →  off
```

Setpoints are whole degrees, because that is what an air conditioner accepts, and they are rounded
**down** — when the choice is between two integers, the colder one wins.

`fan only` is what the unit does when the compressor *cannot* or *need not* run: quiet hours, an
unvented portable unit, the few minutes the compressor is protected after stopping, a standalone
fan that has gone offline, free cooling through an open window, or drying the coil after a cycle.
It is never chosen instead of cooling — a fan moves heat around, it does not remove any.

**Ozone-aware ionizer.** A purifier ionizer produces ozone, itself a lung irritant, so the engine
only runs it in an **empty room** and stands it down the moment you're detected present — the plain
purifier keeps running either way. With no occupancy sensor it assumes you're home and leaves the
ionizer off.

## Portable air conditioners

A portable unit dumps condenser heat down its exhaust hose, so running it unvented actively *heats*
the room. Mark it **portable** and cooling is gated on a real vent signal: either a contact sensor
on the window the hose goes through, or the **Exhaust Vented** switch.

A general door or window sensor will **not** do — an open interior door does not vent the hose.
When it cannot cool, the unit falls back to fan-only to keep air moving. The manual switch
auto-reverts after a few hours, and that deadline survives a restart, so a forgotten toggle cannot
strand the unit into heating the room.

**The vent gate applies whenever an exhaust vent contact is wired, even if you don't tick
"Portable AC".** Cooling *and* drying are both blocked until venting is confirmed — the engine
never runs the compressor into an unvented hose. If you have neither a portable unit nor a vent
contact, there is no hose to vent and no gate.

## What it learns

The engine fits your room's physics online: how fast outdoor heat bleeds in, how much the sun adds,
how much your AC really removes, and how much heat you add just by being in the room. From that it
can answer *"if I do nothing, what will this room read in half an hour?"* and start cooling before
it needs to.

It measures your purifier the same way, so the filter reminder is based on measured loss of
cleaning power rather than an hours guess — and it will tell you when the AC is running but losing,
which is usually a door left open, a dirty filter, or an undersized unit.

It stays honest about all of it. Samples taken with a window open, a mode change mid-interval, a
restart gap, or a sensor glitch are discarded; coefficients are clamped to physically possible
ranges; and until there is enough evidence the engine simply stays reactive rather than acting on a
guess.

## Troubleshooting

**Nothing is happening.** Check **Auto Apply** is on, then the **Blocked** and **Invalid Entities**
sensors.

**It stopped during a storm.** That is the lightning hold. Any strike inside the reaction radius
stops the compressor, and closer or busier storms hold longer.

**A portable AC will not cool.** It needs a vent signal — the exhaust vent contact, or the
**Exhaust Vented** switch. This is deliberate: an unvented portable unit dumps its condenser heat
back into the room, so the engine refuses to cool or dry until venting is confirmed. Flip the
switch on only when the hose is actually out the window.

**Options changed but nothing happened.** Fully restart Home Assistant; a reload is not enough.

**It is cooling less than expected.** Check quiet hours, and whether the room is genuinely above
your target. The **Decision** sensor states its reasoning in plain language.

**Something looks wrong and you want to report it.** Download diagnostics from the integration's
device page — it includes the learned model, which is the only state that cannot be reconstructed
from your config.

## Contributing

Issues and pull requests are welcome. The test suite runs without a Home Assistant install:

```bash
python -m pytest tests/ -q
python -m pyflakes .
```

## License

See the `LICENSE` file in the repository.

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
[release-badge]: https://img.shields.io/github/v/release/swetoast/environment_engine
[release-url]: https://github.com/swetoast/environment_engine/releases
