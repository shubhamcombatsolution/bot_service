# services/strategy_registry.py

class TriggerStrategyRegistry:
    _strategies = {}

    @classmethod
    def register(cls, trigger_type: str, strategy_cls):
        cls._strategies[trigger_type] = strategy_cls

    @classmethod
    def get(cls, trigger_type: str):
        return cls._strategies.get(trigger_type)



