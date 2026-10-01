"""Tests for research_lab/experiments/. Uses the real PostgreSQL-backed
ExperimentRepository and HypothesisRepository."""
import pytest

from research_lab.experiments.lifecycle import VALID_TRANSITIONS, validate_transition
from research_lab.experiments.repository import ExperimentRepository
from research_lab.experiments.service import ExperimentService
from research_lab.exceptions import InvalidExperimentTransitionError
from research_lab.hypothesis.repository import HypothesisRepository
from research_lab.hypothesis.service import HypothesisRegistry
from research_lab.models import ExperimentStatus


# ─────────────────────────────────────────────────────────────────────────
# Lifecycle graph (pure, no I/O)
# ─────────────────────────────────────────────────────────────────────────

def test_draft_can_transition_to_running_or_archived():
    validate_transition(ExperimentStatus.DRAFT, ExperimentStatus.RUNNING)
    validate_transition(ExperimentStatus.DRAFT, ExperimentStatus.ARCHIVED)


def test_draft_cannot_transition_to_completed():
    with pytest.raises(InvalidExperimentTransitionError):
        validate_transition(ExperimentStatus.DRAFT, ExperimentStatus.COMPLETED)


def test_completed_can_go_to_promoted_or_rejected_or_archived():
    validate_transition(ExperimentStatus.COMPLETED, ExperimentStatus.PROMOTED)
    validate_transition(ExperimentStatus.COMPLETED, ExperimentStatus.REJECTED)
    validate_transition(ExperimentStatus.COMPLETED, ExperimentStatus.ARCHIVED)


def test_archived_is_terminal():
    assert VALID_TRANSITIONS[ExperimentStatus.ARCHIVED] == set()
    with pytest.raises(InvalidExperimentTransitionError):
        validate_transition(ExperimentStatus.ARCHIVED, ExperimentStatus.DRAFT)


def test_promoted_and_rejected_can_only_go_to_archived():
    validate_transition(ExperimentStatus.PROMOTED, ExperimentStatus.ARCHIVED)
    validate_transition(ExperimentStatus.REJECTED, ExperimentStatus.ARCHIVED)
    with pytest.raises(InvalidExperimentTransitionError):
        validate_transition(ExperimentStatus.PROMOTED, ExperimentStatus.REJECTED)


# ─────────────────────────────────────────────────────────────────────────
# ExperimentService (real Postgres)
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def service():
    exp_repo = ExperimentRepository()
    hyp_repo = HypothesisRepository()
    svc = ExperimentService(repository=exp_repo, hypothesis_registry=HypothesisRegistry(repository=hyp_repo))
    created = {"experiments": [], "hypotheses": []}
    yield svc, created

    conn = exp_repo._pool.getconn()
    try:
        with conn, conn.cursor() as cur:
            if created["experiments"]:
                cur.execute("DELETE FROM research_experiments WHERE id = ANY(%s)", (created["experiments"],))
    finally:
        exp_repo._pool.putconn(conn)
    conn2 = hyp_repo._pool.getconn()
    try:
        with conn2, conn2.cursor() as cur:
            if created["hypotheses"]:
                cur.execute("DELETE FROM research_hypotheses WHERE id = ANY(%s)", (created["hypotheses"],))
    finally:
        hyp_repo._pool.putconn(conn2)


def test_create_requires_and_registers_a_hypothesis(service):
    svc, created = service
    experiment = svc.create(name="Test Experiment", author="claude", hypothesis_statement="A testable claim")
    created["experiments"].append(experiment.id)
    created["hypotheses"].append(experiment.hypothesis_id)

    assert experiment.status == ExperimentStatus.DRAFT
    assert experiment.hypothesis_id is not None
    hypothesis = svc.hypothesis_registry.get(experiment.hypothesis_id)
    assert hypothesis.statement == "A testable claim"


def test_transition_updates_status_and_persists(service):
    svc, created = service
    experiment = svc.create(name="Test Experiment", author="claude", hypothesis_statement="A testable claim")
    created["experiments"].append(experiment.id)
    created["hypotheses"].append(experiment.hypothesis_id)

    updated = svc.transition(experiment.id, ExperimentStatus.RUNNING)
    assert updated.status == ExperimentStatus.RUNNING

    fetched = svc.get(experiment.id)
    assert fetched.status == ExperimentStatus.RUNNING


def test_transition_rejects_invalid_target(service):
    svc, created = service
    experiment = svc.create(name="Test Experiment", author="claude", hypothesis_statement="A testable claim")
    created["experiments"].append(experiment.id)
    created["hypotheses"].append(experiment.hypothesis_id)

    with pytest.raises(InvalidExperimentTransitionError):
        svc.transition(experiment.id, ExperimentStatus.PROMOTED)


def test_transition_raises_for_unknown_experiment(service):
    svc, _ = service
    with pytest.raises(ValueError):
        svc.transition(999999999, ExperimentStatus.RUNNING)


def test_list_by_status_filters_correctly(service):
    svc, created = service
    experiment = svc.create(name="Filter Test", author="claude", hypothesis_statement="Filterable")
    created["experiments"].append(experiment.id)
    created["hypotheses"].append(experiment.hypothesis_id)

    drafts = svc.list_by_status(ExperimentStatus.DRAFT)
    assert any(e.id == experiment.id for e in drafts)


def test_full_lifecycle_walkthrough(service):
    svc, created = service
    experiment = svc.create(name="Full Lifecycle", author="claude", hypothesis_statement="End to end")
    created["experiments"].append(experiment.id)
    created["hypotheses"].append(experiment.hypothesis_id)

    experiment = svc.transition(experiment.id, ExperimentStatus.RUNNING)
    experiment = svc.transition(experiment.id, ExperimentStatus.COMPLETED)
    experiment = svc.transition(experiment.id, ExperimentStatus.REJECTED)
    experiment = svc.transition(experiment.id, ExperimentStatus.ARCHIVED)
    assert experiment.status == ExperimentStatus.ARCHIVED

    # never deleted - still queryable
    assert svc.get(experiment.id) is not None
