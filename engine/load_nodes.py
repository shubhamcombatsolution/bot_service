# engine/load_nodes.py
import importlib
import pkgutil
import logging

import nodes  # your nodes package

from engine.registry import NODE_REGISTRY


logger = logging.getLogger(__name__)


def load_all_nodes():
    """
    Dynamically imports all modules in the `nodes` package
    so that all @register_node decorators run automatically.
    """
    package = nodes
    prefix = package.__name__ + "."

    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__, prefix):
        if is_pkg:
            continue

        try:
            importlib.import_module(module_name)
        except Exception as exc:
            logger.warning("Skipping node module %s: %s", module_name, exc, exc_info=True)


print("Nodes registered:", NODE_REGISTRY.keys())
