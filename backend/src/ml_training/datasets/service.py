"""OptiTrade ML Training Platform — dataset management service."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional, Tuple

from core.structured_logging import STATUS_SUCCESS, log_event
from ml_training.config import MLTrainingConfig
from ml_training.datasets.builder import DatasetBuilder
from ml_training.datasets.repository import DatasetRepository
from ml_training.features.extractor import FeatureExtractor
from ml_training.models import DatasetType, DatasetVersion, TrainingSample

logger = logging.getLogger(__name__)


class DatasetService:
    """Builds datasets from the Feature Store and persists their
    version metadata (never the samples themselves - always rebuilt on
    demand)."""

    def __init__(
        self,
        builder: Optional[DatasetBuilder] = None,
        repository: Optional[DatasetRepository] = None,
        config: Optional[MLTrainingConfig] = None,
    ) -> None:
        self.config = config or MLTrainingConfig.from_env()
        self.builder = builder or DatasetBuilder(feature_extractor=FeatureExtractor(), config=self.config)
        self.repository = repository or DatasetRepository()

    def build_and_save(
        self,
        symbols: List[str],
        dataset_type: DatasetType,
        start: datetime,
        end: datetime,
        horizons_days: Optional[List[int]] = None,
        step_days: int = 1,
    ) -> Tuple[List[TrainingSample], DatasetVersion]:
        samples, dataset_version = self.builder.build(symbols, dataset_type, start, end, horizons_days, step_days)
        dataset_version.id = self.repository.save(dataset_version)

        log_event(
            logger, component="ml_training", module="ml_training.datasets.service", operation="build_and_save",
            status=STATUS_SUCCESS, dataset_id=dataset_version.id, row_count=dataset_version.row_count,
        )
        return samples, dataset_version

    def get(self, dataset_id: int) -> Optional[DatasetVersion]:
        return self.repository.get(dataset_id)

    def list_by_type(self, dataset_type: Optional[DatasetType] = None, limit: int = 50) -> List[DatasetVersion]:
        return self.repository.list_by_type(dataset_type, limit)
