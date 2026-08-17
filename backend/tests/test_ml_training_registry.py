"""Tests for ml_training/registry/. Real PostgreSQL persistence, real
`research_lab.promotion.service.PromotionService` (backed by real
Continuous Learning / Research Lab Postgres tables)."""
import threading
from datetime import datetime, timezone

import pytest

from learning.models import RollingWindow
from ml_training.exceptions import InvalidPromotionError
from ml_training.models import (
    LabelName,
    ModelAlgorithm,
    ModelRegistryEntry,
    PromotionState,
)
from ml_training.registry.repository import ModelRegistryRepository
from ml_training.registry.service import ModelRegistryService
from research_lab.models import PromotionRecommendation

_MODEL_ID_PREFIX = "registry-svc-test"


def _entry(model_id: str, promotion_state: PromotionState = PromotionState.CANDIDATE) -> ModelRegistryEntry:
    return ModelRegistryEntry(
        model_id=model_id, algorithm=ModelAlgorithm.RANDOM_FOREST, version="v1", dataset_id=None,
        hyperparameters={"n_estimators": 10.0}, metrics=None, feature_list=["f0", "f1"],
        label_name=LabelName.DIRECTION, horizon_days=5, training_date=datetime.now(timezone.utc),
        promotion_state=promotion_state, engine_name=f"MLModel:{model_id}", engine_version="v1",
        artifact_path=f"/tmp/{model_id}.joblib",
    )


@pytest.fixture
def repository():
    repo = ModelRegistryRepository()
    yield repo
    conn = repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ml_training_model_registry WHERE model_id LIKE %s", (f"{_MODEL_ID_PREFIX}%",))
    finally:
        repo._pool.putconn(conn)


@pytest.fixture
def service(repository):
    return ModelRegistryService(repository=repository)


# ─────────────────────────────────────────────────────────────────────────
# repository.py + register/get/list
# ─────────────────────────────────────────────────────────────────────────

def test_register_persists_and_round_trips(service):
    model_id = f"{_MODEL_ID_PREFIX}-register"
    registered = service.register(_entry(model_id))
    assert registered.id is not None

    fetched = service.get(model_id)
    assert fetched is not None
    assert fetched.model_id == model_id
    assert fetched.algorithm == ModelAlgorithm.RANDOM_FOREST
    assert fetched.promotion_state == PromotionState.CANDIDATE
    assert fetched.feature_list == ["f0", "f1"]


def test_register_rejects_non_candidate_state(service):
    with pytest.raises(InvalidPromotionError):
        service.register(_entry(f"{_MODEL_ID_PREFIX}-bad-state", promotion_state=PromotionState.ACTIVE))


def test_get_returns_none_for_unknown_model(service):
    assert service.get(f"{_MODEL_ID_PREFIX}-nonexistent") is None


def test_list_by_state_filters_correctly(service):
    a, b = f"{_MODEL_ID_PREFIX}-list-a", f"{_MODEL_ID_PREFIX}-list-b"
    service.register(_entry(a))
    service.register(_entry(b))
    service.start_shadow(b)

    candidates = service.list_by_state(PromotionState.CANDIDATE)
    shadows = service.list_by_state(PromotionState.SHADOW)
    assert any(entry.model_id == a for entry in candidates)
    assert any(entry.model_id == b for entry in shadows)
    assert all(entry.model_id != b for entry in candidates)


# ─────────────────────────────────────────────────────────────────────────
# lifecycle transitions
# ─────────────────────────────────────────────────────────────────────────

def test_full_lifecycle_candidate_to_shadow_to_active(service):
    model_id = f"{_MODEL_ID_PREFIX}-lifecycle"
    service.register(_entry(model_id))

    shadowed = service.start_shadow(model_id)
    assert shadowed.promotion_state == PromotionState.SHADOW

    activated = service.promote_to_active(model_id, approved_by="hasan")
    assert activated.promotion_state == PromotionState.ACTIVE
    assert activated.approved_by == "hasan"
    assert activated.promoted_at is not None

    fetched = service.get(model_id)
    assert fetched.promotion_state == PromotionState.ACTIVE
    assert fetched.approved_by == "hasan"


def test_promote_to_active_requires_non_blank_approver(service):
    model_id = f"{_MODEL_ID_PREFIX}-blank-approver"
    service.register(_entry(model_id))
    service.start_shadow(model_id)
    with pytest.raises(InvalidPromotionError):
        service.promote_to_active(model_id, approved_by="   ")


def test_promote_to_active_rejects_candidate_skipping_shadow(service):
    model_id = f"{_MODEL_ID_PREFIX}-skip-shadow"
    service.register(_entry(model_id))
    with pytest.raises(InvalidPromotionError):
        service.promote_to_active(model_id, approved_by="hasan")


def test_archive_is_terminal(service):
    model_id = f"{_MODEL_ID_PREFIX}-archive"
    service.register(_entry(model_id))
    archived = service.archive(model_id)
    assert archived.promotion_state == PromotionState.ARCHIVED
    with pytest.raises(InvalidPromotionError):
        service.start_shadow(model_id)


def test_transition_on_unknown_model_raises(service):
    with pytest.raises(InvalidPromotionError):
        service.start_shadow(f"{_MODEL_ID_PREFIX}-never-registered")


# ─────────────────────────────────────────────────────────────────────────
# recommend_promotion (real research_lab.promotion.service.PromotionService)
# ─────────────────────────────────────────────────────────────────────────

def test_recommend_promotion_with_no_evaluated_samples_keeps_shadow(service):
    candidate_id, live_id = f"{_MODEL_ID_PREFIX}-rec-candidate", f"{_MODEL_ID_PREFIX}-rec-live"
    service.register(_entry(candidate_id))
    service.start_shadow(candidate_id)
    service.register(_entry(live_id))
    service.start_shadow(live_id)
    service.promote_to_active(live_id, approved_by="hasan")

    decision = service.recommend_promotion(candidate_id, live_id, window=RollingWindow.THIRTY_DAY)
    assert decision.recommendation == PromotionRecommendation.KEEP_SHADOW
    assert decision.candidate_version == service.get(candidate_id).engine_version
    assert decision.live_version == service.get(live_id).engine_version


def test_recommend_promotion_raises_for_unknown_model(service):
    model_id = f"{_MODEL_ID_PREFIX}-rec-unknown-live"
    service.register(_entry(model_id))
    with pytest.raises(InvalidPromotionError):
        service.recommend_promotion(model_id, f"{_MODEL_ID_PREFIX}-never-registered")


def test_service_defaults_to_real_dependencies():
    svc = ModelRegistryService()
    assert isinstance(svc.repository, ModelRegistryRepository)


# ─────────────────────────────────────────────────────────────────────────
# production/research isolation regression (production audit: "model_serving
# transitively executes research_lab code on every cold start")
#
# ModelRegistryService used to construct a real
# research_lab.promotion.service.PromotionService (and, transitively, its
# own Postgres pool + DDL) unconditionally in __init__ - so every
# model_serving cold start (ModelLoader() -> ModelRegistryService()) ran
# research_lab code purely as a side effect of starting up, even though
# model_serving never calls recommend_promotion. promotion_service is now
# built lazily, only when recommend_promotion is actually invoked.
# ─────────────────────────────────────────────────────────────────────────

def test_construction_never_touches_research_lab(monkeypatch, repository):
    import research_lab.promotion.service as promotion_service_module

    def _fail_if_constructed(self, *args, **kwargs):
        raise AssertionError(
            "research_lab.promotion.service.PromotionService was constructed just by "
            "constructing ModelRegistryService - production/research isolation violated"
        )

    monkeypatch.setattr(promotion_service_module.PromotionService, "__init__", _fail_if_constructed)

    # Must not raise - this is exactly what model_serving/loader.py's
    # ModelLoader() does on every cold start.
    ModelRegistryService(repository=repository)


def test_recommend_promotion_still_lazily_builds_a_real_promotion_service(service):
    candidate_id, live_id = f"{_MODEL_ID_PREFIX}-lazy-candidate", f"{_MODEL_ID_PREFIX}-lazy-live"
    service.register(_entry(candidate_id))
    service.start_shadow(candidate_id)
    service.register(_entry(live_id))
    service.start_shadow(live_id)
    service.promote_to_active(live_id, approved_by="hasan")

    from research_lab.promotion.service import PromotionService

    assert service._promotion_service is None  # not built yet - constructor never touched it
    decision = service.recommend_promotion(candidate_id, live_id, window=RollingWindow.THIRTY_DAY)
    assert decision.recommendation == PromotionRecommendation.KEEP_SHADOW
    assert isinstance(service.promotion_service, PromotionService)
    # Built once, then reused - not reconstructed on every access.
    assert service.promotion_service is service.promotion_service


# ─────────────────────────────────────────────────────────────────────────
# single-ACTIVE-per-group safeguard regression (production audit: "No
# safeguard against two simultaneously-ACTIVE models for the same
# (label, horizon)")
# ─────────────────────────────────────────────────────────────────────────

def test_promote_to_active_demotes_the_previously_active_model(service):
    old_id, new_id = f"{_MODEL_ID_PREFIX}-demote-old", f"{_MODEL_ID_PREFIX}-demote-new"
    service.register(_entry(old_id))
    service.start_shadow(old_id)
    service.promote_to_active(old_id, approved_by="hasan")

    service.register(_entry(new_id))
    service.start_shadow(new_id)
    service.promote_to_active(new_id, approved_by="hasan")

    active = service.list_by_state(PromotionState.ACTIVE)
    active_ids = {e.model_id for e in active if e.model_id in (old_id, new_id)}
    assert active_ids == {new_id}
    assert service.get(old_id).promotion_state == PromotionState.ARCHIVED
    assert service.get(new_id).promotion_state == PromotionState.ACTIVE


def test_promote_to_active_does_not_touch_a_different_groups_active_model(service):
    # A model ACTIVE for a DIFFERENT (label_name, horizon_days) must be
    # completely unaffected by a promotion in another group - the lock
    # (and the demotion) is scoped per-group, never global.
    other_group_id = f"{_MODEL_ID_PREFIX}-other-group-active"
    other_entry = _entry(other_group_id)
    other_entry.horizon_days = 20  # distinct group from the default horizon_days=5
    service.register(other_entry)
    service.start_shadow(other_group_id)
    service.promote_to_active(other_group_id, approved_by="hasan")

    same_group_id = f"{_MODEL_ID_PREFIX}-same-group-active"
    service.register(_entry(same_group_id))
    service.start_shadow(same_group_id)
    service.promote_to_active(same_group_id, approved_by="hasan")

    assert service.get(other_group_id).promotion_state == PromotionState.ACTIVE


def test_concurrent_promotions_for_the_same_group_never_leave_two_models_active():
    # Real, bigger pool: each concurrent promote_to_active call holds a
    # connection for the duration of its locked transaction (see
    # ModelRegistryRepository.locked_group) - the default pool (maxconn=3)
    # would spuriously exhaust under this fixture's own concurrency
    # rather than exercising the lock itself (same reasoning as
    # test_portfolio_service.py's concurrent_repository fixture).
    thread_count = 8
    repository = ModelRegistryRepository(maxconn=thread_count + 2)
    service = ModelRegistryService(repository=repository)
    try:
        model_ids = [f"{_MODEL_ID_PREFIX}-race-{i}" for i in range(thread_count)]
        for model_id in model_ids:
            service.register(_entry(model_id))
            service.start_shadow(model_id)

        errors = []

        def _promote(model_id: str) -> None:
            try:
                service.promote_to_active(model_id, approved_by="hasan")
            except Exception as exc:  # pragma: no cover - failure path only
                errors.append(exc)

        threads = [threading.Thread(target=_promote, args=(mid,)) for mid in model_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        active = [e for e in service.list_by_state(PromotionState.ACTIVE, limit=500) if e.model_id in model_ids]
        assert len(active) == 1, f"expected exactly one ACTIVE model, got {[e.model_id for e in active]}"

        archived_count = sum(
            1 for mid in model_ids if service.get(mid).promotion_state == PromotionState.ARCHIVED
        )
        assert archived_count == thread_count - 1
    finally:
        conn = repository._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM ml_training_model_registry WHERE model_id LIKE %s", (f"{_MODEL_ID_PREFIX}-race-%",),
                )
        finally:
            repository._pool.putconn(conn)
        repository.close()
