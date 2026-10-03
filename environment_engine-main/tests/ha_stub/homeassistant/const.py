from enum import Enum
ATTR_ENTITY_ID = "entity_id"
class Platform(str, Enum):
    SENSOR="sensor"; BINARY_SENSOR="binary_sensor"; SWITCH="switch"; BUTTON="button"
class UnitOfTemperature:
    CELSIUS="°C"; FAHRENHEIT="°F"
