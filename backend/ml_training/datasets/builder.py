"""
OptiTrade ML Training Platform — dataset builder.

Builds datasets directly from the Feature Store. Point-in-time correct
and leakage-free by construction: for every `(symbol, as_of)` point,
features are resolved via `FeatureExtractor.extract` (point-in-time,
`get_feature_as_of`) and labels via `labels.generate_labels` (which
only ever looks *forward* from `as_of`, never backward into the
feature window) - the two never share data from the same side of the
`as_of` boundary.

"Trader" vs "Investor" datasets are simply different horizon sets
(`MLTrainingConfig.trader_horizons_days`/`investor_horizons_days`) over
the same feature/label machinery - not a different pipeline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from core.structured_logging import STATUS_SUCCESS, log_event
from data.fetcher import fetch_price_history_range
from ml_training.config import MLTrainingConfig
from ml_training.features.extractor import FeatureExtractor
from ml_training.labels.generator import PriceFetcher, generate_labels
from ml_training.models import DatasetType, DatasetVersion, LabelName, TrainingSample

logger = logging.getLogger(__name__)


class DatasetBuilder:
    """Pure(ish) builder: has a Feature Store dependency (via
    `FeatureExtractor`) but no persistence of its own - `service.py`
    owns saving the resulting `DatasetVersion`."""

    def __init__(
        self,
        feature_extractor: Optional[FeatureExtractor] = None,
        config: Optional[MLTrainingConfig] = None,
        price_fetcher: Optional[PriceFetcher] = None,
    ) -> None:
        self.config = config or MLTrainingConfig.from_env()
        self.feature_extractor = feature_extractor or FeatureExtractor()
        self.price_fetcher: PriceFetcher = price_fetcher or fetch_price_history_range

    def build(
        self,
        symbols: List[str],
        dataset_type: DatasetType,
        start: datetime,
        end: datetime,
        horizons_days: Optional[List[int]] = None,
        step_days: int = 1,
    ) -> Tuple[List[TrainingSample], DatasetVersion]:
        horizons = horizons_days or (
            self.config.trader_horizons_days if dataset_type == DatasetType.TRADER
            else self.config.investor_horizons_days
        )

        samples: List[TrainingSample] = []
        feature_names_seen: set = set()

        cursor = start
        while cursor <= end:
            for symbol in symbols:
                vector = self.feature_extractor.extract(symbol, cursor)
                if not vector.values:
                    continue
                feature_names_seen.update(vector.values.keys())

                for horizon_days in horizons:
                    label_set = generate_labels(
                        symbol, cursor, horizon_days, vector.values, self.config, self.price_fetcher,
                    )
                    if label_set is None:
                        continue
                    samples.append(
                        TrainingSample(
                            symbol=symbol, as_of=cursor, horizon_days=horizon_days,
                            features=vector.values, labels=label_set,
                        )
                    )
            cursor += timedelta(days=step_days)

        dataset_version = DatasetVersion(
            name=f"{dataset_type.value}-{start.date().isoformat()}-{end.date().isoformat()}",
            dataset_type=dataset_type, symbols=symbols, horizons_days=horizons,
            feature_names=sorted(feature_names_seen), label_names=[label.value for label in LabelName],
            start=start, end=end, row_count=len(samples),
        )

        log_event(
            logger, component="ml_training", module="ml_training.datasets.builder", operation="build",
            status=STATUS_SUCCESS, dataset_type=dataset_type.value, symbol_count=len(symbols),
            horizon_count=len(horizons), row_count=len(samples),
        )
        return samples, dataset_version
