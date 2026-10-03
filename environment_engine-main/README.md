# Environment Engine

[![hacs][hacs-badge]][hacs-url]

An autonomous climate, air-quality and humidity controller for Home Assistant.

You point it at whatever sensors and devices a room already has. It decides when to cool, when a
fan is enough, when to dehumidify, when to shut the blinds, when to seal the flat against outdoor
smoke, when to run the purifier, and when to leave everything alone.

**It never heats.** Cooling, air quality and humidity only, so it will not fight your radiators in
winter.

## Highlights

- **Your setpoint is the setpoint.** Above it, the engine cools. Only a safety hold overrides that:
  not price, not the time of night, not a comfort model.
- **Learns your room.** Fits the actual thermal physics online (envelope leakiness, solar gain, how
  much your AC really removes, the heat you add by being home) and cools *ahead* of the heat.
- **Electricity-aware.** Reads the spot-price forecast and banks cooling while power is cheap.
  Never lets price stop it cooling. Can optionally pre-cool ahead of a forecast hot afternoon
  when power is cheaper now than it will be then.
- **Knows what's in the outside air.** Seals against smoke, pollen or gas, and only runs the
  purifier for the things a filter can actually catch (particulates), not gases it can't.
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

Everything is configured in the UI: **Settings → Devices & Services → Add Integration →
Environment Engine**. Nothing goes in `configuration.yaml`.

There are two kinds of entry.

### Global entry (add this once)

Shared outdoor data, so you set it once rather than repeating it per room. Every field is optional.

| Field | Used for |
|---|---|
| Weather (outdoor) | Outdoor temperature and the forecast |
| Forecast source | Forecast highs, for pre-cooling before a hot afternoon |
| Outdoor air quality (AQI or PM) | Sealing the home during a smoke event |
| Outdoor pollen (grains/m³) | Sealing + purifying during a pollen peak. Filterable, so the purifier helps |
| Outdoor gas (ozone / CO / NO₂) | Sealing during a gas event. A filter can't scrub gases, so it seals only |
| Energy price | Shifting cooling toward cheap power |
| Average / reference price | Deciding what counts as expensive |
| Price forecast | Finding the cheapest upcoming window |
| Lightning sensor (Blitzortung) | Stopping everything during a storm |

### Room entry (add one per room)

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

> After changing anything in the config flow, **fully restart Home Assistant**. A reload is not
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
| Pollen threshold | 1.0 grains/m³ | Outdoor pollen level at which the home seals and the purifier runs. |
| Pre-cool ahead of forecast heat | Off | Opt-in. Banks cooling before a hot afternoon when power is cheaper now than then. Only ever cools harder, never stops the engine cooling a hot room. |
| Pre-cool before quiet hours | Off | Opt-in. If the learned model predicts the night will pass the quiet-hours limit, cools ahead of the quiet window. Needs quiet hours and a few days of learning. |
| Portable AC | Off | Gates cooling on a real vent signal. See below. |
| Auto Apply | Off | Master switch: decide only, or actually act. |

## Entities

Each room entry creates:

| Entity | Type | Tells you |
|---|---|---|
| Decision | Sensor | What the engine is doing right now, per device, in plain language |
| Cooling Demand | Sensor (%) | How strongly the room wants cooling, and the reasoning behind it |
| Effectiveness | Sensor (%) | How well each system performs vs this room's own best: climate, air, humidity, whichever it has |
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
are context, and context may only ever make it cool *harder*, never less, and never "the room is
fine actually".

```
safety blocked (smoke / lightning / outlet)   →  everything off
above your setpoint, compressor available     →  cool
above your setpoint, compressor blocked       →  fan only
at setpoint but the air is too damp           →  dry
otherwise                                     →  off
```

Setpoints are whole degrees, because that is what an air conditioner accepts, and they are rounded
**down**: when the choice is between two integers, the colder one wins.

`fan only` is what the unit does when the compressor *cannot* or *need not* run: quiet hours, an
unvented portable unit, the few minutes the compressor is protected after stopping, a standalone
fan that has gone offline, free cooling through an open window, or drying the coil after a cycle.
It is never chosen instead of cooling. A fan moves heat around, it does not remove any.

Cooling starts when the room rises above your number. On a hot or damp day the engine drives the
unit a degree or two below it, and a cycle that has started runs until the room reaches that lower
number, so the compressor is not switched off and on around a single reading. On a mild day the
two numbers are the same, and once the engine has learned the room it stops slightly below yours
(see *What it learns*).

Night, expensive power and an open window can ease off *extra* cooling (the degrees the engine
drives below your number on a hot day). They cannot lift the setpoint above your number.

**The fan and the purifier are independent.** The fan runs for heat (circulation, a comfort breeze,
pulling cooler air through an open window) and for damp (airflow against mould). The purifier runs
for air quality and nothing else. A fan filters nothing, so bad air never starts it, and heat never
starts the purifier. Each device is commanded on its own channel, so a change to one does not
re-send the other.

**An empty home.** Cooling stops, apart from capping the drift and drying a damp flat. Blinds keep
shading. The purifier keeps following the air: it runs if the air needs it and switches off when it
is clean.

**Ozone-aware ionizer.** A purifier ionizer produces ozone, itself a lung irritant, so the engine
only runs it in an **empty room** and stands it down the moment you're detected present. The plain
purifier keeps running either way. With no occupancy sensor it assumes you're home and leaves the
ionizer off.

## Outdoor air: pollen, smoke and gas

Sealing the home helps against some outdoor threats and not others, so the engine treats them
differently instead of collapsing everything into one number:

- **Particulates: smoke, PM, pollen.** A HEPA filter genuinely catches these, so the engine
  seals *and* runs the purifier hard. Wire your pollen sensor (grains/m³) into the pollen slot and
  hay-fever season is handled automatically.
- **Gases: ozone, CO, NO₂, SO₂.** A filter can't scrub a gas, so the engine seals to keep it out
  but does **not** ramp the purifier. Running it would just waste filter life pretending to help.

Both the outdoor air-quality and pollen sensors carry a forecast, so the engine also **airs out
pre-emptively**: if the room is getting stuffy and outdoor air is about to turn bad, it opens up now,
while the outside is still clean, because once the threat arrives the window has to shut.

## Portable air conditioners

A portable unit dumps condenser heat down its exhaust hose, so running it unvented actively *heats*
the room. Mark it **portable** and cooling is gated on a real vent signal: either a contact sensor
on the window the hose goes through, or the **Exhaust Vented** switch.

A general door or window sensor will **not** do: an open interior door does not vent the hose.
When it cannot cool, the unit falls back to fan-only to keep air moving. The manual switch
auto-reverts after a few hours, and that deadline survives a restart, so a forgotten toggle cannot
strand the unit into heating the room.

**The vent gate applies whenever an exhaust vent contact is wired, even if you don't tick
"Portable AC".** Cooling *and* drying are both blocked until venting is confirmed. The engine
never runs the compressor into an unvented hose. If you have neither a portable unit nor a vent
contact, there is no hose to vent and no gate.

## What it learns

The engine fits your room's physics as it runs: how fast outdoor heat gets in, how much the sun
adds and at which hours, how much your AC really removes, and how much heat people add by being in
the room. Readings are folded into ten-minute windows first, so an ordinary 0.1 °C sensor is good
enough. Nothing learned is used until the fit is trusted, which takes about half a day of clean
data, and everything is kept across restarts.

What the learning changes:

| Learned | Used for |
|---|---|
| How fast the room regains heat | Stopping a cooling cycle a little below your setpoint on mild days, just far enough that the compressor rests for a full minimum cycle. Never more than 1 °C. |
| Sun gain by hour of day | Knowing when *this* room takes sun. A west-facing room heats at 17:00, not at noon. Used when there is no light sensor. |
| The night ahead | Optional pre-cooling before quiet hours, so the compressor can stay off while you sleep. |
| Gap between the unit's sensor and yours | If the unit's own sensor reads colder than the room it would stop short, so it is sent a lower setpoint. A unit that reads warmer needs nothing and gets nothing. |
| AC cooling rate | **Struggling To Cool** and the climate figure on **Effectiveness**. |
| Purifier cleaning rate | **Filter Due**, from measured loss of cleaning power instead of an hours guess. |
| Heat nobody explained | **Unexplained Heat**: a window left open, an oven, a drifting sensor. |

Every one of these can only make the engine cool harder or earlier. None of them can raise your
setpoint or delay cooling a room that is above it.

The **Effectiveness** sensor shows one number per system, measured against the best level *this*
room has sustained, not an assumed ideal, so it works for any hardware. A sustained drop means
something changed. It reads "learning" until it has a baseline.

Samples taken with a window open, across a restart gap, during a sensor glitch or while someone
arrives are thrown away. Coefficients are clamped to physically possible ranges. **Reset Learning**
clears all of it.

## Troubleshooting

**Nothing is happening.** Check **Auto Apply** is on, then the **Blocked** and **Invalid Entities**
sensors.

**It stopped during a storm.** That is the lightning hold. Any strike inside the reaction radius
stops the compressor, and closer or busier storms hold longer.

**A portable AC will not cool.** It needs a vent signal: the exhaust vent contact, or the
**Exhaust Vented** switch. This is deliberate: an unvented portable unit dumps its condenser heat
back into the room, so the engine refuses to cool or dry until venting is confirmed. Flip the
switch on only when the hose is actually out the window.

**Options changed but nothing happened.** Fully restart Home Assistant; a reload is not enough.

**It is cooling less than expected.** Check quiet hours, and whether the room is genuinely above
your target. The **Decision** sensor states its reasoning in plain language.

**The fan and the purifier start together.** They should not: the fan answers heat and damp, the
purifier answers air quality, and neither reads the other's signal. If they move together, check
**Invalid Entities** for an entity listed "in both" slots. A fan and a purifier both live in Home
Assistant's `fan` domain, so it is easy to put the purifier in the fan slot. Give each device its
own slot. Until you do, the purifier slot wins and the fan channel leaves that entity alone.

**A device was offline when the engine decided.** Its command is kept and sent once the device is
available again. **Apply Decision** re-sends everything immediately.

**Something looks wrong and you want to report it.** Download diagnostics from the integration's
device page. It includes the learned model, which is the only state that cannot be reconstructed
from your config.

## Contributing

Issues and pull requests are welcome. The test suite runs without a Home Assistant install:

```bash
python -m pytest tests/ -q
python -m pyflakes custom_components
```

## License

See the `LICENSE` file in the repository.

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://github.com/hacs/integration
[release-badge]: https://img.shields.io/github/v/release/swetoast/environment_engine
[release-url]: https://github.com/swetoast/environment_engine/releases
