class DataUpdateCoordinator:
    def __class_getitem__(cls, i): return cls
    def __init__(self, *a, **k): pass
    def async_add_listener(self, cb): return lambda: None
class CoordinatorEntity:
    def __class_getitem__(cls, i): return cls
    def __init__(self, coordinator): self.coordinator = coordinator
