"""
OptiTrade Engine Registry — automatic engine discovery.

Importing a package that contains self-registering engine modules is
enough to populate the registry: each engine module registers its own
instance (conventionally into `engine_registry.registry.default_registry`)
as a side effect of being imported — this function's only job is to make
sure every submodule under a given package actually gets imported.

No concrete voting engine packages exist yet (Technical/Fundamental/News
engines are later steps); this is exercised in tests against a small
fixture package of self-registering fake engines
(`tests/fixtures/fake_engines/`).
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import List

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event

logger = logging.getLogger(__name__)


def discover_engines(package_name: str) -> List[str]:
    """Imports every submodule under `package_name` (recursively),
    triggering any self-registration each module performs at import time.
    Returns the dotted names of every module successfully imported. A
    single submodule failing to import is logged and skipped rather than
    aborting discovery of the rest.
    """
    package = importlib.import_module(package_name)
    imported: List[str] = []

    module_infos = list(pkgutil.walk_packages(package.__path__, prefix=f"{package_name}."))
    for _, module_name, _ in module_infos:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            log_event(
                logger,
                component="engine_registry",
                module="engine_registry.discovery",
                operation="discover_engines",
                status=STATUS_ERROR,
                error_type=type(exc).__name__,
                discovered_module=module_name,
            )
            continue
        imported.append(module_name)

    log_event(
        logger,
        component="engine_registry",
        module="engine_registry.discovery",
        operation="discover_engines",
        status=STATUS_SUCCESS,
        package_name=package_name,
        modules_imported=len(imported),
    )
    return imported
