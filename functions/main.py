"""Cloud Functions for Firebase entry point.

Deploy with `firebase deploy --only functions` from the repo root; the predeploy hook in
firebase.json copies the backend package (`backend/src/aimuse`) next to this file first.

Settings (functions/.env, or the environment):
  AIMUSE_ENGINE     lyria (default) | fake  - "fake" makes synthetic audio, for the emulator
  AIMUSE_MODEL      lyria-3.5 (default) | lyria-3-clip-preview
  AIMUSE_DAILY_USD  per-user daily spending cap, default 1.00
  AIMUSE_STYLE_MODEL  text model that turns "like <artist>" into musical traits,
                    default gemini-3.8-flash
  AIMUSE_ALLOWED_EMAILS  comma-separated emails allowed to make songs (invite-only).
                    Empty = nobody, "*" = anyone signed in.
Secret: GEMINI_API_KEY (`firebase functions:secrets:set GEMINI_API_KEY`).
"""

from __future__ import annotations

import json
import os

from firebase_admin import auth, firestore, initialize_app, storage
from firebase_functions import firestore_fn, https_fn, options
from firebase_functions.params import SecretParam

GEMINI_API_KEY = SecretParam("GEMINI_API_KEY")

initialize_app()


def _clients():
    """Firestore client and Storage bucket. The emulators need no credentials, but the Admin SDK
    insists on finding some, so connect to them directly with anonymous credentials."""
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return firestore.client(), storage.bucket()
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore as gfirestore
    from google.cloud import storage as gstorage

    config = json.loads(os.environ.get("FIREBASE_CONFIG") or "{}")
    project = config.get("projectId") or os.environ.get("GCLOUD_PROJECT", "demo-aimuse")
    if os.environ.get("FIREBASE_STORAGE_EMULATOR_HOST"):
        os.environ.setdefault(
            "STORAGE_EMULATOR_HOST", f"http://{os.environ['FIREBASE_STORAGE_EMULATOR_HOST']}"
        )
    creds = AnonymousCredentials()
    db = gfirestore.Client(project=project, credentials=creds)
    bucket = gstorage.Client(project=project, credentials=creds).bucket(
        config.get("storageBucket") or f"{project}.appspot.com"
    )
    return db, bucket


def _is_allowed(uid: str) -> bool:
    """Invite-only: the user's (verified) email must be in AIMUSE_ALLOWED_EMAILS."""
    allowed = {
        e.strip().lower()
        for e in os.environ.get("AIMUSE_ALLOWED_EMAILS", "").split(",")
        if e.strip()
    }
    if "*" in allowed:
        return True
    if not allowed:
        return False
    user = auth.get_user(uid)
    return bool(user.email and user.email_verified and user.email.lower() in allowed)


def _translator():
    from aimuse.inspiration import FakeStyleTranslator, GeminiStyleTranslator

    if os.environ.get("AIMUSE_ENGINE", "lyria") == "fake":
        return FakeStyleTranslator()
    return GeminiStyleTranslator(
        GEMINI_API_KEY.value, model=os.environ.get("AIMUSE_STYLE_MODEL", "gemini-3.8-flash")
    )


def _engine():
    from aimuse.engines import FakeEngine, LyriaEngine

    if os.environ.get("AIMUSE_ENGINE", "lyria") == "fake":
        return FakeEngine(max_seconds=30)
    return LyriaEngine(GEMINI_API_KEY.value, model=os.environ.get("AIMUSE_MODEL", "lyria-3.5"))


@firestore_fn.on_document_created(
    document="users/{uid}/jobs/{jobId}",
    secrets=[GEMINI_API_KEY],
    memory=options.MemoryOption.GB_2,
    timeout_sec=540,
    max_instances=10,
)
def on_job_created(event: firestore_fn.Event) -> None:
    # Imported here, not at module level: the audio stack (scipy via pyloudnorm, librosa) takes
    # ~10 s to import cold, and Firebase gives function discovery only 10 s at deploy time.
    from firebase_stores import FirestoreJobStore, StorageAudioStore
    from muse_jobs import process_job

    db, bucket = _clients()
    process_job(
        event.params["uid"],
        event.params["jobId"],
        store=FirestoreJobStore(db),
        audio=StorageAudioStore(bucket),
        engine_factory=_engine,
        daily_cap_usd=float(os.environ.get("AIMUSE_DAILY_USD", "1.00")),
        is_allowed=_is_allowed,
        translator_factory=_translator,
    )


@https_fn.on_call(secrets=[GEMINI_API_KEY], memory=options.MemoryOption.MB_512, max_instances=5)
def describe_artist(req: https_fn.CallableRequest) -> dict:
    """Preview what "In the spirit of <artist>" will mean (genre, era, singer, voice) before a
    song is made. Uses the same cached description as the song, so what you see is what's sent."""
    from aimuse.inspiration import InspirationError
    from firebase_stores import FirestoreJobStore
    from muse_jobs import describe_reference

    Code = https_fn.FunctionsErrorCode
    if req.auth is None:
        raise https_fn.HttpsError(Code.UNAUTHENTICATED, "Sign in first.")
    if not _is_allowed(req.auth.uid):
        raise https_fn.HttpsError(Code.PERMISSION_DENIED, "This app is invite-only.")
    reference = (req.data or {}).get("reference") if isinstance(req.data, dict) else None
    if not isinstance(reference, str):
        raise https_fn.HttpsError(Code.INVALID_ARGUMENT, "Missing reference.")
    db, _ = _clients()
    try:
        return describe_reference(reference, FirestoreJobStore(db), _translator)
    except InspirationError as e:
        raise https_fn.HttpsError(Code.INVALID_ARGUMENT, str(e)) from e
