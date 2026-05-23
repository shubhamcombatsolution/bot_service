from typing import Type
from engine.export_strategies.base import IExportStrategy


class ExportStrategyFactory:
    """Factory + registry for all export strategies."""
    _registry = {}

    @classmethod
    def register(cls, export_type: str):
        """Decorator to register new export strategy (case-insensitive)."""
        def wrapper(strategy_class: Type[IExportStrategy]):
            normalized = export_type.strip().lower()   # ✅ normalize
            cls._registry[normalized] = strategy_class
            return strategy_class
        return wrapper

    @classmethod
    def get_strategy(cls, export_type: str) -> IExportStrategy:
        """Return an instance of the strategy based on export type."""
        if not export_type:
            raise ValueError("export_type is required")

        normalized = export_type.strip().lower()      # ✅ normalize

        strategy_class = cls._registry.get(normalized)

        if not strategy_class:
            raise ValueError(
                f"No export strategy registered for type: {export_type}"
            )

        return strategy_class()                       # ✅ create instance only here
