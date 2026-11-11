# aimuse
Use agentic AI to create your music for you to listen to from today to your end 

AI Muse learns your musical taste and generates custom, consistent,
downloadable tracks without making you write prompts. It starts with Google's
Lyria models through the Gemini API and keeps the engine layer pluggable.

- 📄 **[Research & product plan](docs/PLAN.md)** covers the vision, model
  research, architecture, roadmap and decisions.
- 📱 **[The app](docs/APP.md)**: web app (`web/`) and Cloud Functions (`functions/`) on
  Firebase. It covers how it works, how to run it locally for free (`./scripts/dev.sh`), its
  tests and how to deploy.
- 🎛️ **[Backend core](backend/README.md)** is the Python package that compiles
  prompts, calls Lyria, analyses and ranks tracks. Its tests run on GitHub
  Actions, and a manually started workflow runs paid Lyria experiments.

Status: deployed on Firebase and in use. Sign in, pick a station and mood (or paste a story or
your own lyrics, in English, Spanish, Persian and more), get a song, then play, download and
rate it.

## Deployment: the steps that actually worked

This is the exact sequence used for the first deploy from **Google Cloud Shell**, including the
two errors a brand-new project hits and their fixes. Replace `PROJECT_ID` and
`PROJECT_NUMBER` with your own; the error messages print both.

### 1. Firebase console (browser, once)
1. Create the project, then **Upgrade** to the **Blaze** (pay-as-you-go) plan. Cloud Functions
   need it. Set a budget alert when asked.
2. **Build → Authentication → Get started → Google → Enable → Save.**
3. **Build → Firestore Database → Create database**, production mode. Pick the location
   carefully: the function is deployed next to it (`eur3` put the function in
   `europe-west1`).
4. **Build → Storage → Get started**, production mode, same location.

### 2. Cloud Shell: code, login and settings
Open Cloud Shell from the Google Cloud console. `firebase`, `gcloud` and `python3.12` are
already installed there.

```bash
git clone https://github.com/rezap/aimuse.git && cd aimuse
firebase login --no-localhost
firebase use --add                  # pick the project, alias "default"
gcloud config set project PROJECT_ID
```

Web app settings. `firebase apps:sdkconfig web` prints the values; put them in
`web/.env.local` with these names (see `web/.env.example`):
```bash
firebase apps:create web aimuse-web     # once per project
firebase apps:sdkconfig web
nano web/.env.local
```
```
NEXT_PUBLIC_FIREBASE_API_KEY=...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=...
NEXT_PUBLIC_FIREBASE_PROJECT_ID=...
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=...
NEXT_PUBLIC_FIREBASE_APP_ID=...
```

Who may make songs and the daily spend cap per person, then the Gemini key. The key is pasted
at the prompt and stored in Secret Manager, never in a file:
```bash
printf 'AIMUSE_ALLOWED_EMAILS=you@gmail.com\nAIMUSE_DAILY_USD=1.00\n' > functions/.env
firebase functions:secrets:set GEMINI_API_KEY
```

The Python environment the Firebase CLI uses to read the functions:
```bash
python3.12 -m venv functions/venv && functions/venv/bin/pip install -r functions/requirements.txt
```

### 3. Grant the service-agent roles before the first deploy
On a new project the first `firebase deploy` stopped with *"We failed to modify the IAM policy
for the project"* and printed the first three commands below; running them fixed it. The
fourth is the fix for the Eventarc error in step 4. Running all four up front avoids both
failures:
```bash
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=serviceAccount:service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com \
  --role=roles/iam.serviceAccountTokenCreator
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com \
  --role=roles/run.invoker
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com \
  --role=roles/eventarc.eventReceiver
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=serviceAccount:service-PROJECT_NUMBER@gcp-sa-eventarc.iam.gserviceaccount.com \
  --role=roles/eventarc.serviceAgent
```
Find `PROJECT_NUMBER` with `gcloud projects describe PROJECT_ID --format='value(projectNumber)'`.
If a command says the service account doesn't exist yet, run `firebase deploy --only functions`
once (it enables the APIs and creates those accounts), then run the commands again.

### 4. Deploy: functions first, then everything
```bash
firebase deploy --only functions
```
On a brand-new project this can still fail with *"Permission denied while using the Eventarc
Service Agent … it may take a few minutes"*. That is Google's one-time setup delay: wait about
5 minutes and run the same command again. It succeeded on the retry.

Then the website, database rules and storage rules:
```bash
firebase deploy
```
The app is at `https://PROJECT_ID.web.app` (printed as *Hosting URL*). The warning
*"GOOGLE_CLOUD_QUOTA_PROJECT is not usable when uploading source"* is harmless.

### 5. Every update after that
```bash
cd ~/aimuse && git pull && firebase deploy --only functions,hosting,firestore
```
If only the web page changed, `firebase deploy --only hosting` is enough.

### If something is off
| You see | Fix |
|---|---|
| `PERMISSION_DENIED` from `gcloud` | Cloud Shell is logged in as an account that isn't the project's Owner: check `gcloud auth list`, then `gcloud auth login` with the right one |
| "Firebase isn't configured" in the app | `web/.env.local` was missing at deploy time: fix it, then `firebase deploy --only hosting` |
| "This app is invite-only…" | your Google email isn't in `functions/.env` exactly: fix it, then `firebase deploy --only functions` |
| A song stays on "Waiting…" or fails | `firebase functions:log` shows why |
| Deploy times out reading the functions | module-level imports are too slow (Firebase allows 10 s): keep heavy imports inside the handler, as `functions/main.py` does |
