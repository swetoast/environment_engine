# Environment Engine

[![hacs][hacs-badge]][hacs-url]

An autonomous climate, air-quality and humidity controller for Home Assistant.

You point it at whatever sensors and devices a room already has. It decides when to cool, when a
fan is enough, when to dehumidify, when to shut the blinds, when to seal the flat against outdoor
smoke, when to run the purifier — and when to leave everything alone.

**It never heats.** Cooling, air quality and humidity only, so it will not fight your radiators in
winter.

## Highlights

- **Your setpoint is the setpoint.** Above it, the engine cools. Only a safety hold overrides that
  — not price, not the time of night, not a comfort model.
- **Learns your room.** Fits the actual thermal physics online (envelope leakiness, solar gain, how
  much your AC really removes, the heat you add by being home) and cools *ahead* of the heat.
- **Electricity-aware.** Reads the spot-price forecast and banks cooling while power is cheap.
  Never lets price stop it cooling.
- **Safety first.** Smoke, an overloaded outlet, or nearby lightning stop everything immediately.
- **Works with what you have.** Every sensor and device slot is optional. A room with one fan and a
  thermometer still gets sensible behaviour.

## Requirements

- Home Assistant **2024.6** or newer (the config flow uses collapsible sections)
- At least one climate, fan or purifier entity to control
- No external dependencies, no cloud, no API keys

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/swetoast/environment-engine` as an **Integration**.
3. Search for **Environment Engine** and install it.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/environment_engine` into your Home Assistant `config/custom_components`
   directory.
2. Restart Home Assistant.

## Configuration

All configuration is through the UI — **Settings → Devices & Services → Add Integration →
Environment Engine**. There is nothing to put in `configuration.yaml`.

You add two kinds of entry.

### 1. Global entry (once)

Shared outdoor data, so you set it once rather than per room. Every field is optional.

| Field | Used for |
|---|---|
| Weather (outdoor) | Outdoor temperature, the forecast |
| Weather / forecast source | Forecast highs for pre-cooling |
| Outdoor air quality (AQI or PM) | Sealing the home during smoke events |
| Energy price | Shifting cooling toward cheap power |
| Average / reference price | Deciding what counts as expensive |
| Price forecast | Finding the cheapest upcoming window |
| Lightning sensor (Blitzortung) | Stopping everything during a storm |

### 2. Room entry (one per room)

Point it at what that room actually has. **Every slot is optional and accepts multiple entities.**

**Climate & comfort** — air conditioner / heat pump, indoor temperature, fan, blinds, light level

**Air quality** — AQI, PM1/PM2.5, PM10, purifier, purifier ionizer, ventilation, CO₂, VOC

**Humidity** — indoor humidity, humidifier / dehumidifier

**Presence & safety** — occupancy, window/door contact, smoke alarm, outlet overload, exhaust vent
contact

Turn on **Auto Apply** when you are ready to let it act. Until then it decides and reports but
changes nothing, which is a good way to watch what it would do first.

> After changing anything in the config flow, **fully restart Home Assistant** — not just reload.
> Home Assistant caches integration translations.

## Options

Every option has inline help in the config flow. These are the ones that most change how it feels.

| Option | Default | What it does |
|---|---|---|
| Target temperature | 22 °C | The number. Above it, the engine cools. |
| Humidity sensitivity | Normal | The dew point at which damp air starts costing a degree of setpoint, and at which dehumidifying kicks in. Tolerant 17 °C / Normal 15 / Sensitive 13 / Very sensitive 11. |
| Quiet hours | Off | A window where the compressor is held back and the unit fans instead. |
| Cool anyway above | 26 °C | Hard limit during quiet hours. Cross it and the compressor runs, full stop. |
| Let an empty home drift up to | 4 °C | How far above target an unoccupied room may get before the engine caps it. Stops you walking into a 31 °C flat. `0` disables. |
| Dry the coil after cooling | 120 s | Fan runs on after a cycle to evaporate the wet coil — this is what stops an AC smelling. `0` disables. |
| Portable AC | Off | Gates cooling on a real vent signal. See below. |
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
| Reset Learning | Button | Clear what the engine has learned about this room |

## How it decides

Only one rule really matters: **above your setpoint means cool.** Humidity and outdoor heat are
context, and context may only ever make it cool *harder* — never less, and never "the room is fine
actually".

```
safety blocked (smoke / lightning / outlet)  →  everything off
above your setpoint, compressor available    →  cool
above your setpoint, compressor blocked      →  fan only
at setpoint but the air is too damp          →  dry
otherwise                                    →  off
```

Everything is in whole degrees, because that is what an air conditioner accepts, and the setpoint
is rounded **down** — when the choice is between two integers, the colder one wins.

## Portable air conditioners

A portable unit dumps condenser heat down its exhaust hose, so running it unvented actively *heats*
the room. Mark it **portable** and cooling is gated on a real vent signal: either a contact sensor
on the window the hose goes through, or the **Exhaust Vented** switch.

A general door or window sensor will **not** do — an open interior door does not vent the hose.
When it cannot cool, the unit falls back to fan-only to keep air moving.

## What it learns

The engine fits your room's actual physics online — how fast outdoor heat bleeds in, how much the
sun adds, how much your AC really removes, and how much heat you add just by being home. From that
it can answer "if I do nothing, what will this room read in half an hour?" and start cooling before
it needs to.

It also measures what your purifier actually achieves, so the filter reminder is based on measured
degradation rather than an hours guess, and flags when the AC is running but losing — usually a
door left open, a dirty filter, or an undersized unit.

It stays honest about all of it: dirty samples (open window, mid-interval mode change, restart gaps,
sensor spikes) are discarded, coefficients are clamped to physically possible ranges, and until
there is enough evidence the engine simply stays reactive.

## Troubleshooting

**It is not doing anything.** Check **Auto Apply** is on. Check the **Blocked** and **Invalid
Entities** sensors.

**It stopped during a storm.** That is the lightning hold. Any strike within the reaction radius
stops the compressor; closer and busier storms hold longer.

**A portable AC will not cool.** It needs a vent signal — the exhaust vent contact, or the
**Exhaust Vented** switch.

**Options changed but nothing happened.** Fully restart Home Assistant; a reload is not enough.

**It is cooling less than expected.** Check quiet hours, and whether the room is genuinely above
your target. The Decision sensor states its reasoning in plain language.

## Contributing

Issues and pull requests are welcome. The test suite runs with no Home Assistant install:

```bash
python -m pytest tests/ -q
python -m pyflakes .
```

## License

See the `LICENSE` file in the repository.

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
[release-badge]: https://img.shields.io/github/v/release/swetoast/environment-engine
[release-url]: https://github.com/swetoast/environment-engine/releases
