from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timezone
from .const import ACTION_NONE, ACTION_OFF, ACTION_ON, HVAC_COOL, HVAC_DRY
from .decision import Decision
_MISSING = object()
_SPEED_RANK = {"low": 1, "medium": 2, "high": 3}
_COMPRESSOR = {HVAC_COOL, HVAC_DRY}  # modes that actually run the compressor


def _simple_actions(decision: Decision):
    """(channel, action) pairs for the plain on/off-style channels, which all
    rate-limit and commit identically (unlike hvac/target/fan/purifier_speed)."""
    return (
        ("cover", decision.cover_action),
        ("purifier", decision.purifier_action),
        ("humidifier", decision.humidifier_action),
        ("ionizer", decision.ionizer_action),
    )


class HysteresisEngine:
    """Rate-limits how often each output channel may change.

    The engine tracks the value last *committed* to each channel (the last real
    command it emitted) together with the time of that commit. A suppressed
    change is emitted as ACTION_NONE / a held value, but it does NOT update the
    committed value or its timestamp -- so a held channel never resets its own
    clock and never corrupts the next comparison.
    """
    def __init__(self) -> None:
        self.last_decision: Decision | None = None
        self._committed: dict[str, object] = {}
        self._changed_at: dict[str, datetime] = {}

    def _allowed(self, channel: str, minimum_interval: int) -> bool:
        last = self._changed_at.get(channel)
        if last is None:
            return True
        return (datetime.now(timezone.utc) - last).total_seconds() >= minimum_interval

    def apply(self, decision: Decision, minimum_interval: int, compressor_min_cycle: int = 0, device_min_cycle: int = 0) -> Decision:
        if not self._committed or decision.blocked:
            self._commit(decision)
            self.last_decision = decision
            return decision
        hvac_mode = decision.hvac_mode
        target = decision.target_temperature
        fan_action = decision.fan_action
        fan_speed = decision.fan_speed
        purifier_speed = decision.purifier_speed
        committed_fan = self._committed.get("fan", (ACTION_NONE, None))
        if hvac_mode is not None and hvac_mode != self._committed.get("hvac") and not self._allowed("hvac", minimum_interval):
            hvac_mode = self._committed.get("hvac")
        # Compressor anti-short-cycle: don't flip the compressor on<->off (cool/dry
        # vs anything else) more often than the minimum cycle time protects it.
        if compressor_min_cycle > 0 and hvac_mode is not None:
            committed_hvac = self._committed.get("hvac")
            if (hvac_mode in _COMPRESSOR) != (committed_hvac in _COMPRESSOR) and not self._allowed("compressor", compressor_min_cycle):
                hvac_mode = committed_hvac
        if target != self._committed.get("target") and not self._allowed("target", minimum_interval):
            target = self._committed.get("target")
        if fan_action != ACTION_OFF and (fan_action, fan_speed) != committed_fan and not self._allowed("fan", minimum_interval):
            fan_action = ACTION_NONE
            fan_speed = committed_fan[1]
        # Wear protection: don't start<->stop the fan more often than device_min_cycle.
        if device_min_cycle > 0 and fan_action != ACTION_NONE and (fan_action == ACTION_ON) != (committed_fan[0] == ACTION_ON) and not self._allowed("fan_cycle", device_min_cycle):
            fan_action = ACTION_NONE
            fan_speed = committed_fan[1]
        ventilation_action = decision.ventilation_action
        if ventilation_action not in (ACTION_NONE, ACTION_OFF) and ventilation_action != self._committed.get("ventilation") and not self._allowed("ventilation", minimum_interval):
            ventilation_action = ACTION_NONE
        # plain on/off channels share one rule
        gated = {}
        for channel, value in _simple_actions(decision):
            if value != ACTION_NONE and value != self._committed.get(channel) and not self._allowed(channel, minimum_interval):
                value = ACTION_NONE
            gated[channel] = value
        # Wear protection: don't start<->stop the purifier more often than device_min_cycle.
        committed_purifier = self._committed.get("purifier")
        if device_min_cycle > 0 and gated["purifier"] != ACTION_NONE and (gated["purifier"] == ACTION_ON) != (committed_purifier == ACTION_ON) and not self._allowed("purifier_cycle", device_min_cycle):
            gated["purifier"] = committed_purifier if committed_purifier is not None else gated["purifier"]
        # purifier speed downshifts (to a quieter speed) wait twice as long as
        # ramping up, so a brief dip in pollutant level doesn't drop the fan early
        committed_speed = self._committed.get("purifier_speed")
        if purifier_speed is not None and purifier_speed != committed_speed and committed_speed is not None:
            downshift = _SPEED_RANK.get(purifier_speed, 0) < _SPEED_RANK.get(committed_speed, 0)
            interval = minimum_interval * 2 if downshift else minimum_interval
            if not self._allowed("purifier_speed", interval):
                purifier_speed = committed_speed
        final = replace(
            decision, hvac_mode=hvac_mode, target_temperature=target, fan_action=fan_action, fan_speed=fan_speed,
            cover_action=gated["cover"], purifier_action=gated["purifier"], humidifier_action=gated["humidifier"],
            ionizer_action=gated["ionizer"], purifier_speed=purifier_speed, ventilation_action=ventilation_action,
        )
        self._commit(final)
        self.last_decision = final
        return final

    def _commit(self, decision: Decision) -> None:
        now = datetime.now(timezone.utc)
        prev_hvac = self._committed.get("hvac")
        if decision.hvac_mode is not None and (prev_hvac in _COMPRESSOR) != (decision.hvac_mode in _COMPRESSOR):
            self._changed_at["compressor"] = now  # compressor just started or stopped
        prev_fan_on = self._committed.get("fan", (ACTION_NONE, None))[0] == ACTION_ON
        if decision.fan_action != ACTION_NONE and (decision.fan_action == ACTION_ON) != prev_fan_on:
            self._changed_at["fan_cycle"] = now  # fan just started or stopped
        prev_pur_on = self._committed.get("purifier") == ACTION_ON
        if decision.purifier_action != ACTION_NONE and (decision.purifier_action == ACTION_ON) != prev_pur_on:
            self._changed_at["purifier_cycle"] = now  # purifier just started or stopped
        if decision.hvac_mode is not None:
            self._set("hvac", decision.hvac_mode, now)
        elif "hvac" not in self._committed:
            self._set("hvac", None, now)
        self._set("target", decision.target_temperature, now)
        if decision.fan_action != ACTION_NONE:
            self._set("fan", (decision.fan_action, decision.fan_speed), now)
        elif "fan" not in self._committed:
            self._set("fan", (ACTION_NONE, decision.fan_speed), now)
        for channel, value in _simple_actions(decision):
            if value != ACTION_NONE:
                self._set(channel, value, now)
            elif channel not in self._committed:
                self._set(channel, ACTION_NONE, now)
        if decision.purifier_speed is not None:
            self._set("purifier_speed", decision.purifier_speed, now)
        if decision.ventilation_action != ACTION_NONE:
            self._set("ventilation", decision.ventilation_action, now)
        elif "ventilation" not in self._committed:
            self._set("ventilation", ACTION_NONE, now)

    def _set(self, channel: str, value, now: datetime) -> None:
        if self._committed.get(channel, _MISSING) != value:
            self._changed_at[channel] = now
        self._committed[channel] = value
