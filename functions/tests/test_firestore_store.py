"""FirestoreJobStore against the Firestore emulator (skipped unless FIRESTORE_EMULATOR_HOST)."""

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="needs the Firestore emulator"
)


@pytest.fixture
def store():
    from google.cloud import firestore

    from firebase_stores import FirestoreJobStore

    return FirestoreJobStore(firestore.Client(project="demo-aimuse"))


def test_claim_complete_and_spend(store):
    uid, job_id = f"u-{uuid.uuid4().hex[:8]}", "job1"
    jobs = store.db.collection("users").document(uid).collection("jobs")
    jobs.document(job_id).set({"status": "queued", "stationId": "late-night-lofi"})

    assert store.claim_job(uid, job_id)["stationId"] == "late-night-lofi"
    assert store.claim_job(uid, job_id) is None  # already running

    assert store.reserve_spend(uid, "2026-10-28", 0.08, 0.10)
    assert not store.reserve_spend(uid, "2026-10-28", 0.08, 0.10)
    assert store.reserve_spend(uid, "2026-10-29", 0.08, 0.10)  # new day resets

    store.complete_job(uid, job_id, {"title": "t", "rating": 0})
    assert jobs.document(job_id).get().get("status") == "done"
    track = store.db.collection("users").document(uid).collection("tracks").document(job_id).get()
    assert track.get("title") == "t" and track.get("createdAt") is not None

    jobs.document("job2").set({"status": "queued"})
    store.fail_job(uid, "job2", "nope")
    assert jobs.document("job2").get().get("error") == "nope"


def test_influence_cache(store):
    assert store.get_influence("nobody-xyz") is None
    store.save_influence("bob-dylan", "Bob Dylan", {"genres": ["folk rock"]})
    assert store.get_influence("bob-dylan") == {"genres": ["folk rock"]}
