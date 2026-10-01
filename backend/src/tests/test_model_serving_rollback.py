"""Tests for model_serving/rollback.py. Real PostgreSQL throughout - its
own `model_serving_rollback_overrides` table, plus real
`ml_training.registry` entries to validate against (no artifact
loading/prediction is exercised here, so a fake artifact_path is fine)."""
from datetime import datetime, timezone

import pytest

from ml_training.models import LabelName, ModelAlgorithm, ModelRegistryEntry, PromotionState
from ml_training.registry.repository import ModelRegistryRepository
from ml_training.registry.service import ModelRegistryService
from model_serving.exceptions import InvalidRollbackError, ModelVersionNotFoundError
from model_serving.rollback import RollbackRepository, RollbackService

_MODEL_ID_PREFIX = "rollback-test"


def _entry(model_id: str, horizon_days: int = 1, promotion_state=PromotionState.CANDIDATE) -> ModelRegistryEntry:
    return ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={}, metrics=None, feature_list=["f0"], label_name=LabelName.DIRECTION,
        horizon_days=horizon_days, training_date=datetime.now(timezone.utc), promotion_state=promotion_state,
        engine_name=f"MLModel:{model_id}", engine_version="v1", artifact_path=f"/tmp/{model_id}.joblib",
    )


@pytest.fixture
def registry_service():
    repo = ModelRegistryRepository()
    svc = ModelRegistryService(repository=repo)
    yield svc
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ml_training_model_registry WHERE model_id LIKE %s", (f"{_MODEL_ID_PREFIX}%",))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def rollback_repository():
    repo = RollbackRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM model_serving_rollback_overrides WHERE model_id LIKE %s", (f"{_MODEL_ID_PREFIX}%",))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def service(registry_service, rollback_repository):
    return RollbackService(repository=rollback_repository, registry_service=registry_service)


def test_no_override_by_default(service):
    assert service.current_override(LabelName.DIRECTION, 1) is None


def test_rollback_to_sets_and_current_override_reads_it_back(registry_service, service):
    model_id = f"{_MODEL_ID_PREFIX}-target"
    registry_service.register(_entry(model_id))

    service.rollback_to(LabelName.DIRECTION, 1, model_id, rolled_back_by="ops")
    override = service.current_override(LabelName.DIRECTION, 1)
    assert override is not None
    assert override.model_id == model_id


def test_rollback_to_requires_non_blank_approver(registry_service, service):
    model_id = f"{_MODEL_ID_PREFIX}-blank-approver"
    registry_service.register(_entry(model_id))
    with pytest.raises(InvalidRollbackError):
        service.rollback_to(LabelName.DIRECTION, 1, model_id, rolled_back_by="   ")


def test_rollback_to_raises_for_unknown_model_id(service):
    with pytest.raises(ModelVersionNotFoundError):
        service.rollback_to(LabelName.DIRECTION, 1, f"{_MODEL_ID_PREFIX}-never-registered", rolled_back_by="ops")


def test_rollback_to_raises_when_label_or_horizon_mismatch(registry_service, service):
    model_id = f"{_MODEL_ID_PREFIX}-wrong-horizon"
    registry_service.register(_entry(model_id, horizon_days=5))
    with pytest.raises(InvalidRollbackError):
        service.rollback_to(LabelName.DIRECTION, 1, model_id, rolled_back_by="ops")


def test_rollback_never_touches_the_registrys_promotion_state(registry_service, service):
    model_id = f"{_MODEL_ID_PREFIX}-no-mutation"
    registry_service.register(_entry(model_id))
    service.rollback_to(LabelName.DIRECTION, 1, model_id, rolled_back_by="ops")

    entry = registry_service.get(model_id)
    assert entry.promotion_state == PromotionState.CANDIDATE  # unchanged - rollback never mutates ml_training.registry


def test_rollback_to_overwrites_a_previous_override_for_the_same_key(registry_service, service):
    first_id, second_id = f"{_MODEL_ID_PREFIX}-first", f"{_MODEL_ID_PREFIX}-second"
    registry_service.register(_entry(first_id))
    registry_service.register(_entry(second_id))

    service.rollback_to(LabelName.DIRECTION, 1, first_id, rolled_back_by="ops")
    service.rollback_to(LabelName.DIRECTION, 1, second_id, rolled_back_by="ops")
    assert service.current_override(LabelName.DIRECTION, 1).model_id == second_id


def test_clear_rollback_removes_the_override(registry_service, service):
    model_id = f"{_MODEL_ID_PREFIX}-to-clear"
    registry_service.register(_entry(model_id))
    service.rollback_to(LabelName.DIRECTION, 1, model_id, rolled_back_by="ops")
    service.clear_rollback(LabelName.DIRECTION, 1)
    assert service.current_override(LabelName.DIRECTION, 1) is None


def test_clear_rollback_is_a_no_op_when_nothing_was_overridden(service):
    service.clear_rollback(LabelName.DIRECTION, 999)  # must not raise


def test_service_defaults_to_real_dependencies():
    svc = RollbackService()
    assert isinstance(svc.repository, RollbackRepository)
    assert isinstance(svc.registry_service, ModelRegistryService)
