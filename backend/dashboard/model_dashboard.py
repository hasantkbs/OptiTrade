"""
OptiTrade Analytics & Dashboard Platform — ML dashboard.

Registry/training-run/promotion-decision/benchmark data all comes from
`dashboard/repository.py`'s raw-SQL reads of `ml_training`/`research_lab`
tables (never a Python import of either package - see that module's
docstring). Feature importance history comes from the Feature Store
instead, since `ml_training.importance.service.FeatureImportanceService`
already persists it there (`{method}_importance:{feature_name}`) as a
matter of policy, alongside Research Lab.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event
from dashboard.config import DashboardConfig
from dashboard.models import (
    ActiveModelInfo,
    BenchmarkSnapshot,
    FeatureImportanceSnapshot,
    MLDashboardView,
    PromotionHistoryEntry,
    RegistryEntrySnapshot,
    ShadowModelInfo,
    TrainingRunSnapshot,
)
from dashboard.repository import DashboardRepository
from feature_store.service import FeatureStoreService

logger = logging.getLogger(__name__)
_MODULE = "dashboard.model_dashboard"
_COMPONENT = "dashboard"

_IMPORTANCE_METHODS = ("shap", "permutation")
_IMPORTANCE_HISTORY_DAYS = 90


class ModelDashboardService:
    def __init__(
        self,
        repository: DashboardRepository,
        feature_store: Optional[FeatureStoreService] = None,
        config: Optional[DashboardConfig] = None,
    ) -> None:
        self._repository = repository
        self._feature_store = feature_store or FeatureStoreService()
        self._config = config or DashboardConfig.from_env()

    def build(self, feature_importance_model_ids: Optional[List[str]] = None) -> MLDashboardView:
        started_at = time.perf_counter()
        limit = self._config.recent_history_limit

        view = MLDashboardView(
            active_models=self._active_models(),
            shadow_models=[
                ShadowModelInfo(
                    model_id=row["model_id"], algorithm=row["algorithm"], version=row["version"],
                    label_name=row["label_name"], horizon_days=row["horizon_days"], training_date=row["training_date"],
                )
                for row in self._repository.list_registry_entries(promotion_state="shadow", limit=limit)
            ],
            registry_entries=[self._to_registry_snapshot(row) for row in self._repository.list_registry_entries(limit=limit)],
            training_runs=[
                TrainingRunSnapshot(
                    model_id=row["model_id"], algorithm=row["algorithm"], task_type=row["task_type"],
                    status=row["status"], metrics=row["metrics"] or {}, training_date=row["training_date"],
                )
                for row in self._repository.list_training_runs(limit=limit)
            ],
            promotion_history=self._promotion_history(limit),
            benchmark_history=[
                BenchmarkSnapshot(
                    subject_type=row["subject_type"], subject_a=row["subject_a"], subject_b=row["subject_b"],
                    window_name=row["window_name"], p_value=row["p_value"], significant=row["significant"],
                    created_at=row["created_at"],
                )
                for row in self._repository.list_benchmark_results(limit=limit)
            ],
            feature_importance_history=self._feature_importance_history(feature_importance_model_ids or []),
        )
        log_event(
            logger, component=_COMPONENT, module=_MODULE, operation="build", status=STATUS_SUCCESS,
            execution_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return view

    def _active_models(self) -> List[ActiveModelInfo]:
        overrides = {(row["label_name"], row["horizon_days"]): row for row in self._repository.list_rollback_overrides()}
        models = []
        for row in self._repository.list_registry_entries(promotion_state="active", limit=self._config.recent_history_limit):
            key = (row["label_name"], row["horizon_days"])
            override = overrides.get(key)
            models.append(
                ActiveModelInfo(
                    model_id=override["model_id"] if override else row["model_id"],
                    label_name=row["label_name"], horizon_days=row["horizon_days"], algorithm=row["algorithm"],
                    version=row["version"], promoted_at=row["promoted_at"], is_rollback_override=override is not None,
                )
            )
        return models

    def _to_registry_snapshot(self, row: dict) -> RegistryEntrySnapshot:
        return RegistryEntrySnapshot(
            model_id=row["model_id"], algorithm=row["algorithm"], version=row["version"],
            promotion_state=row["promotion_state"], label_name=row["label_name"], horizon_days=row["horizon_days"],
            engine_name=row["engine_name"], metrics=row["metrics"] or {}, training_date=row["training_date"],
            promoted_at=row["promoted_at"],
        )

    def _promotion_history(self, limit: int) -> List[PromotionHistoryEntry]:
        entries = []
        for row in self._repository.list_promotion_decisions(limit=limit):
            applied_entry = self._repository.find_active_registry_version(row["engine_name"], row["candidate_version"])
            entries.append(
                PromotionHistoryEntry(
                    engine_name=row["engine_name"], candidate_version=row["candidate_version"],
                    live_version=row["live_version"], recommendation=row["recommendation"], rationale=row["rationale"],
                    candidate_accuracy=row["candidate_accuracy"], live_accuracy=row["live_accuracy"],
                    decided_at=row["decided_at"], applied=applied_entry is not None,
                    applied_at=applied_entry["promoted_at"] if applied_entry else None,
                )
            )
        return entries

    def _feature_importance_history(self, model_ids: List[str]) -> List[FeatureImportanceSnapshot]:
        """One model_id's (or one feature's) Feature Store lookup
        failing is logged and skipped rather than losing every other
        model's feature importance history - or, since this feeds
        `build()`'s single `MLDashboardView`, the entire ML dashboard
        (registry/training-run/promotion/benchmark data, all already
        successfully fetched by the time this runs)."""
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=_IMPORTANCE_HISTORY_DAYS)
        snapshots: List[FeatureImportanceSnapshot] = []
        for model_id in model_ids:
            try:
                feature_names = self._feature_store.list_feature_names(model_id)
            except Exception as exc:
                log_event(
                    logger, component=_COMPONENT, module=_MODULE, operation="list_feature_names",
                    status=STATUS_ERROR, model_id=model_id, error_type=type(exc).__name__, level=logging.WARNING,
                )
                continue

            for feature_name in feature_names:
                method = next((m for m in _IMPORTANCE_METHODS if feature_name.startswith(f"{m}_importance:")), None)
                if method is None:
                    continue
                actual_feature_name = feature_name[len(f"{method}_importance:"):]
                try:
                    history = self._feature_store.get_feature_history(model_id, feature_name, start, end)
                except Exception as exc:
                    log_event(
                        logger, component=_COMPONENT, module=_MODULE, operation="get_feature_history",
                        status=STATUS_ERROR, model_id=model_id, feature_name=feature_name,
                        error_type=type(exc).__name__, level=logging.WARNING,
                    )
                    continue
                for record in history:
                    snapshots.append(
                        FeatureImportanceSnapshot(
                            model_id=model_id, method=method, feature_name=actual_feature_name,
                            importance=record.value, computed_at=record.event_timestamp,
                        )
                    )
        return snapshots
