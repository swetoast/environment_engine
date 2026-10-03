class SensorEntity: pass
class RestoreSensor(SensorEntity): pass
class SensorDeviceClass:
    TEMPERATURE="temperature"; DURATION="duration"; ENUM="enum"; HUMIDITY="humidity"
class SensorStateClass:
    MEASUREMENT="measurement"; TOTAL="total"; TOTAL_INCREASING="total_increasing"
