"""OptiTrade Research Lab — dataset management service."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

import pandas as pd

from core.structured_logging import STATUS_SUCCESS, log_event
from feature_store.service import FeatureStoreService
from research_lab.datasets import builder
from research_lab.datasets.repository import DatasetRepository
from research_lab.models import DatasetDefinition

logger = logging.getLogger(__name__)


class DatasetService:
    """Defines reproducible historical datasets and rebuilds them on
    demand from the Feature Store - never persists a redundant copy of
    the underlying feature values."""

    def __init__(
        self,
        feature_store: Optional[FeatureStoreService] = None,
        repository: Optional[DatasetRepository] = None,
    ) -> None:
        self.feature_store = feature_store or FeatureStoreService()
        self.repository = repository or DatasetRepository()

    def define(
        self, name: str, symbols: List[str], feature_names: List[str],
        start: datetime, end: datetime, version: str = "v1",
    ) -> DatasetDefinition:
        definition = DatasetDefinition(
            name=name, symbols=symbols, feature_names=feature_names, start=start, end=end, version=version,
        )
        definition.id = self.repository.save(definition)
        log_event(
            logger, component="research_lab", module="research_lab.datasets.service", operation="define",
            status=STATUS_SUCCESS, dataset_id=definition.id, symbol_count=len(symbols),
            feature_count=len(feature_names),
        )
        return definition

    def get_definition(self, definition_id: int) -> Optional[DatasetDefinition]:
        return self.repository.get(definition_id)

    def list_definitions(self, limit: int = 50) -> List[DatasetDefinition]:
        return self.repository.list_all(limit)

    def build(self, definition_id: int) -> pd.DataFrame:
        definition = self.repository.get(definition_id)
        if definition is None:
            raise ValueError(f"no dataset definition with id {definition_id}")
        dataframe = builder.build(definition, self.feature_store)
        log_event(
            logger, component="research_lab", module="research_lab.datasets.service", operation="build",
            status=STATUS_SUCCESS, dataset_id=definition_id, row_count=len(dataframe),
        )
        return dataframe
