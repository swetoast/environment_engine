class ConfigEntry: pass
class ConfigFlow:
    def __init_subclass__(cls, **kw): pass
class OptionsFlow: pass
class OptionsFlowWithConfigEntry(OptionsFlow): pass
