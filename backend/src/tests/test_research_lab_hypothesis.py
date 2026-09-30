"""Tests for research_lab/hypothesis/. Uses the real PostgreSQL-backed
HypothesisRepository."""
import pytest

from research_lab.hypothesis import HypothesisRegistry
from research_lab.hypothesis.repository import HypothesisRepository
from research_lab.models import HypothesisOutcome


@pytest.fixture
def registry():
    repo = HypothesisRepository()
    created_ids = []
    reg = HypothesisRegistry(repository=repo)
    yield reg, created_ids
    if created_ids:
        conn = repo._pool.getconn()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM research_hypotheses WHERE id = ANY(%s)", (created_ids,),
                )
        finally:
            repo._pool.putconn(conn)


def test_register_persists_and_returns_an_id(registry):
    reg, created_ids = registry
    hypothesis = reg.register("Momentum features improve BUY precision")
    created_ids.append(hypothesis.id)
    assert hypothesis.id is not None
    assert hypothesis.outcome is None


def test_resolve_updates_outcome_and_evidence(registry):
    reg, created_ids = registry
    hypothesis = reg.register("Testing resolution")
    created_ids.append(hypothesis.id)

    resolved = reg.resolve(hypothesis.id, HypothesisOutcome.ACCEPTED, ["precision rose"])
    assert resolved.outcome == HypothesisOutcome.ACCEPTED
    assert resolved.evidence == ["precision rose"]
    assert resolved.resolved_at is not None


def test_get_returns_none_for_unknown_id(registry):
    reg, _ = registry
    assert reg.get(999999999) is None


def test_list_by_outcome_filters_correctly(registry):
    reg, created_ids = registry
    accepted = reg.register("Accepted hypothesis")
    rejected = reg.register("Rejected hypothesis")
    created_ids.extend([accepted.id, rejected.id])

    reg.resolve(accepted.id, HypothesisOutcome.ACCEPTED, ["evidence a"])
    reg.resolve(rejected.id, HypothesisOutcome.REJECTED, ["evidence b"])

    accepted_only = reg.list_by_outcome(HypothesisOutcome.ACCEPTED)
    assert any(h.id == accepted.id for h in accepted_only)
    assert all(h.id != rejected.id for h in accepted_only)


def test_never_deleted_stays_queryable_after_rejection(registry):
    reg, created_ids = registry
    hypothesis = reg.register("A hypothesis that will fail")
    created_ids.append(hypothesis.id)
    reg.resolve(hypothesis.id, HypothesisOutcome.REJECTED, ["it failed"])

    still_there = reg.get(hypothesis.id)
    assert still_there is not None
    assert still_there.outcome == HypothesisOutcome.REJECTED


def test_registry_defaults_to_real_repository():
    reg = HypothesisRegistry()
    assert isinstance(reg.repository, HypothesisRepository)
