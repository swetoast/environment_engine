class Store:
    def __init__(self, *a, **k): pass
    def async_delay_save(self, fn, delay=0): self.saved = fn()
    async def async_load(self): return None
