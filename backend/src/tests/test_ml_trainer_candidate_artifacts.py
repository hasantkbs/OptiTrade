"""
Regression tests for research/ml_trainer.py's versioned candidate
artifact writing (Task 0.2-A, CTO Remediation Plan Revision 4, Finding
A9): main.py's self_evolution_loop calls `train()` with no arguments
(default `output_suffix=""`), which previously went straight to
`_deploy_if_not_regressed` against the exact file `core/ml_predictor.py`
loads for production - an automatic, daily, ungated overwrite of a
live-serving model. `write_candidate_artifact` replaces that: every
default-suffix training run now writes a new, uniquely-identified file
under `model_artifacts/candidates/` and never touches the live artifact
at all. Registering a candidate into `ml_training.registry` and
promoting one to live-served are Task 0.2-B/C's job, explicitly out of
scope here - nothing in this file exercises or imports that package.

All tests use `tmp_path` and a small fake joblib module - no real
XGBoost/yfinance training, no real `model_artifacts/` directory, and no
access to the live, permission-restricted `xgb_signal_model.joblib`
anywhere in this file.
"""
import os

import joblib
import pytest

from research.ml_trainer import (
    CandidateAlreadyExistsError,
    CandidateArtifact,
    write_candidate_artifact,
)


def _package(accuracy: float, marker: str) -> dict:
    return {"model": marker, "cv_accuracy_mean": accuracy, "cv_accuracy_std": 0.01}


@pytest.fixture
def candidates_dir(tmp_path):
    return str(tmp_path / "candidates")


# ── Requirement 1: written to a versioned, separate path ──────────────────

def test_candidate_is_written_to_a_versioned_path_under_the_candidates_dir(candidates_dir):
    candidate = write_candidate_artifact(_package(0.60, "first"), joblib, candidates_dir)

    assert isinstance(candidate, CandidateArtifact)
    assert os.path.dirname(candidate.path) == candidates_dir
    assert candidate.candidate_id in os.path.basename(candidate.path)
    assert joblib.load(candidate.path)["model"] == "first"


def test_candidates_dir_is_created_if_it_does_not_exist_yet(tmp_path):
    candidates_dir = str(tmp_path / "does" / "not" / "exist" / "yet")
    assert not os.path.exists(candidates_dir)

    candidate = write_candidate_artifact(_package(0.60, "first"), joblib, candidates_dir)

    assert os.path.exists(candidate.path)


# ── Requirement 2: two writes produce distinct paths ───────────────────────

def test_two_candidate_writes_produce_distinct_paths_and_ids(candidates_dir):
    first = write_candidate_artifact(_package(0.55, "first"), joblib, candidates_dir)
    second = write_candidate_artifact(_package(0.65, "second"), joblib, candidates_dir)

    assert first.path != second.path
    assert first.candidate_id != second.candidate_id
    assert joblib.load(first.path)["model"] == "first"
    assert joblib.load(second.path)["model"] == "second"


# ── Requirement 3 (live artifact untouched) + 6 (live serving path) ───────

def test_writing_a_candidate_never_creates_or_touches_a_file_named_like_the_live_artifact(candidates_dir, tmp_path):
    live_path = tmp_path / "xgb_signal_model.joblib"
    live_path.write_bytes(b"pretend this is the live model - must never change")
    original_bytes = live_path.read_bytes()

    write_candidate_artifact(_package(0.60, "candidate"), joblib, candidates_dir)

    assert live_path.read_bytes() == original_bytes
    assert not (tmp_path / "xgb_signal_model.joblib.bak").exists()
    # The candidate directory is a sibling, never nested under/mixed
    # with wherever the live artifact lives.
    assert os.path.commonpath([candidates_dir, str(live_path)]) == str(tmp_path)
    assert candidates_dir != str(live_path)


# ── Requirement 4 + 5: collision/overwrite protection, atomicity ──────────

def test_a_duplicate_candidate_id_is_never_silently_overwritten(candidates_dir, monkeypatch):
    import research.ml_trainer as ml_trainer

    monkeypatch.setattr(ml_trainer, "_generate_candidate_id", lambda created_at: "fixed-id")

    first = write_candidate_artifact(_package(0.60, "first"), joblib, candidates_dir)
    first_bytes_on_disk = open(first.path, "rb").read()

    with pytest.raises(CandidateAlreadyExistsError):
        write_candidate_artifact(_package(0.90, "second"), joblib, candidates_dir)

    # The original candidate must be byte-for-byte unchanged - the
    # collision must be refused, not resolved by overwriting.
    assert open(first.path, "rb").read() == first_bytes_on_disk
    assert joblib.load(first.path)["model"] == "first"


def test_a_failed_write_leaves_no_partial_or_temp_file_behind(candidates_dir):
    class _ExplodingJoblib:
        @staticmethod
        def dump(package, path):
            raise OSError("simulated: disk full mid-write")

    with pytest.raises(OSError, match="simulated: disk full mid-write"):
        write_candidate_artifact(_package(0.60, "doomed"), _ExplodingJoblib, candidates_dir)

    assert os.listdir(candidates_dir) == []


def test_a_failed_link_due_to_collision_leaves_no_temp_file_behind(candidates_dir, monkeypatch):
    import research.ml_trainer as ml_trainer

    monkeypatch.setattr(ml_trainer, "_generate_candidate_id", lambda created_at: "fixed-id")
    write_candidate_artifact(_package(0.60, "first"), joblib, candidates_dir)

    with pytest.raises(CandidateAlreadyExistsError):
        write_candidate_artifact(_package(0.90, "second"), joblib, candidates_dir)

    leftovers = [f for f in os.listdir(candidates_dir) if f.endswith(".joblib.tmp")]
    assert leftovers == []


# ── Requirement 7: metadata sufficient for a future registry adapter ──────

def test_returned_metadata_identifies_the_artifact_for_a_future_registry_adapter(candidates_dir):
    candidate = write_candidate_artifact(_package(0.60, "first"), joblib, candidates_dir)

    assert isinstance(candidate.candidate_id, str) and candidate.candidate_id
    assert os.path.isabs(candidate.path) or os.path.exists(candidate.path)
    assert candidate.created_at is not None
    # The path alone is enough to load the full package (metrics,
    # feature_names, etc.) back out - no extra lookup required.
    reloaded = joblib.load(candidate.path)
    assert reloaded["cv_accuracy_mean"] == 0.60


# ── Requirement 9: the legacy serving path must not pick up candidates ────

def test_legacy_predictor_does_not_load_a_freshly_written_candidate(candidates_dir, monkeypatch, tmp_path):
    import core.ml_predictor as ml_predictor

    monkeypatch.setattr(ml_predictor, "_MODEL_CACHE", None)
    live_path = str(tmp_path / "xgb_signal_model.joblib")  # deliberately does not exist
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", live_path)

    write_candidate_artifact(_package(0.60, "candidate"), joblib, candidates_dir)

    assert ml_predictor.is_model_available() is False
