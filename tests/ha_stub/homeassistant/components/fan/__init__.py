from enum import IntFlag
class FanEntityFeature(IntFlag):
    SET_SPEED=1; OSCILLATE=2; DIRECTION=4; PRESET_MODE=8; TURN_OFF=16; TURN_ON=32
