"""Firestore / Cloud Storage implementations of the job store interfaces."""

from __future__ import annotations

from google.cloud import firestore


class FirestoreJobStore:
    def __init__(self, db: firestore.Client):
        self.db = db

    def _job(self, uid: str, job_id: str):
        return self.db.collection("users").document(uid).collection("jobs").document(job_id)

    def claim_job(self, uid: str, job_id: str) -> dict | None:
        ref = self._job(uid, job_id)

        @firestore.transactional
        def claim(tx) -> dict | None:
            snap = ref.get(transaction=tx)
            if not snap.exists or snap.get("status") != "queued":
                return None
            tx.update(ref, {"status": "running", "updatedAt": firestore.SERVER_TIMESTAMP})
            return snap.to_dict()

        return claim(self.db.transaction())

    def reserve_spend(self, uid: str, day: str, usd: float, cap_usd: float) -> bool:
        ref = self.db.collection("users").document(uid)

        @firestore.transactional
        def reserve(tx) -> bool:
            snap = ref.get(transaction=tx)
            spend = (snap.to_dict() or {}).get("spend", {}) if snap.exists else {}
            spent = spend.get("usd", 0.0) if spend.get("day") == day else 0.0
            if spent + usd > cap_usd + 1e-9:
                return False
            tx.set(ref, {"spend": {"day": day, "usd": round(spent + usd, 4)}}, merge=True)
            return True

        return reserve(self.db.transaction())

    def complete_job(self, uid: str, job_id: str, track: dict) -> None:
        user = self.db.collection("users").document(uid)
        batch = self.db.batch()
        batch.set(
            user.collection("tracks").document(job_id),
            {**track, "createdAt": firestore.SERVER_TIMESTAMP},
        )
        batch.update(
            self._job(uid, job_id),
            {"status": "done", "trackId": job_id, "updatedAt": firestore.SERVER_TIMESTAMP},
        )
        batch.commit()

    def fail_job(self, uid: str, job_id: str, message: str) -> None:
        self._job(uid, job_id).update(
            {"status": "failed", "error": message[:500], "updatedAt": firestore.SERVER_TIMESTAMP}
        )


class StorageAudioStore:
    def __init__(self, bucket):
        self.bucket = bucket

    def upload(self, path: str, data: bytes, content_type: str) -> None:
        blob = self.bucket.blob(path)
        blob.upload_from_string(data, content_type=content_type)
