# AI Muse app: how it fits together

```
 Browser (web/, Next.js static PWA)
   │  1. sign in (Firebase Auth, Google)
   │  2. add  users/{uid}/jobs/{id}  {stationId, mood, theme, energy, vocals, status: "queued"}
   ▼
 Firestore ──trigger──► Cloud Function on_job_created (functions/, Python)
                          3. claim job (queued → running), check the user's daily budget
                          4. backend pipeline: prompt → Lyria → analyse
                          5. audio → Storage  users/{uid}/tracks/{id}.mp3
                          6. write users/{uid}/tracks/{id}, job → done (or failed + reason)
   ▲
   │  7. the page listens to jobs and tracks live: progress, then a playable song with
   │     download, 👍/👎 and lyrics
 Browser
```

- **Security**: `firestore.rules` and `storage.rules`. Users only see their own data. The app
  can only *queue* a valid request, and only the function writes songs. Users can rate or
  delete their own songs. Tests are in `web/tests/rules.test.mjs`.
- **Invite-only**: only signed-in users whose verified Google email is in
  `AIMUSE_ALLOWED_EMAILS` (in `functions/.env`) can make songs. Everyone else gets a polite
  "invite-only" message, and nothing is spent. `*` lets anyone in.
- **Artist style ("In the spirit of…")**: the listener can name an artist or band. A Gemini
  text model (`AIMUSE_STYLE_MODEL`, default `gemini-3.8-flash`) turns it into musical traits
  only: genre, era, instruments, production, vocal delivery and lyric style. Any word of the
  name that leaks into the traits is removed, so only the traits reach Lyria and the song is
  original. Traits are cached per artist in the server-only `influences` collection, so the
  same artist always gives the same description. If translation fails, the song is still
  made, with a note.
- **Own lyrics**: "✍️ Use my own lyrics" (or pasting multi-line text into the topic field)
  sends up to 3000 characters. They go to Lyria under a `Lyrics:` header with `[Verse n]`
  tags (the listener's own tags are kept), always sung, and the song length follows the
  text. Lyria refuses well-known songs and famous poems; the app explains that refusal
  instead of showing a raw API error.
- **Cost control**: the function reserves the request's price against a per-user daily cap
  (`AIMUSE_DAILY_USD`, default $1.00 = 12 full songs) *before* calling Lyria. Duplicate
  trigger deliveries are ignored, because a job is claimed only once.
- **Stations** come from `backend/src/aimuse/presets/*.json`. The web app copies them at build
  time (`web/scripts/sync-stations.mjs`), so the UI and the function always agree.

## Run it locally (no Firebase project, no cost)

Needs Python 3.12, Node 22 and Java 21.

```bash
./scripts/dev.sh
```

This starts the Firebase emulators (Auth, Firestore, Storage, Functions) and the web app at
http://localhost:3000. Click **Test user (emulator)**, then make a song. Songs come from the
**fake engine**, which makes synthetic audio, so it's free. To hear real Lyria songs locally,
set `AIMUSE_ENGINE=lyria` in `functions/.env.local` and your key in `functions/.secret.local`.

## Tests (GitHub Actions → App CI, runs on every push and PR)

| Job | What it checks |
|---|---|
| Web build | TypeScript and the static production build |
| Functions unit tests | Job processing with in-memory stores: happy path, duplicate trigger, daily cap, bad input, engine errors |
| Security rules + end-to-end | Rules tests and the Firestore adapter on the emulators. Then a real browser signs in, makes a song (fake engine), plays and downloads it, and rates it. Screenshots are uploaded as an artifact. |

Run the end-to-end test yourself with `./scripts/e2e.sh`.

## Deploy from Google Cloud Shell (simplest first deploy)

In the Firebase console, first:
1. Switch the project to the **Blaze** plan and set a budget alert.
2. **Authentication** → Get started → **Google** → Enable.
3. **Firestore Database** → Create database → production mode, location `nam5 (us-central)`.
4. **Storage** → Get started → production mode, same location.

Then, in Cloud Shell:

```bash
git clone https://github.com/rezap/aimuse.git && cd aimuse
firebase login --no-localhost                       # skip if already logged in
firebase use --add YOUR_PROJECT_ID                  # pick the project, alias "default"

# Web app config -> web/.env.local
firebase apps:create web aimuse-web                 # once; prints an App ID
firebase apps:sdkconfig web                          # shows apiKey, authDomain, ...
#   copy those into web/.env.local (see web/.env.example for the names)

# Who may make songs, and the daily cap per person
printf 'AIMUSE_ALLOWED_EMAILS=you@gmail.com\nAIMUSE_DAILY_USD=1.00\n' > functions/.env

# Gemini key into Secret Manager (paste it when asked)
firebase functions:secrets:set GEMINI_API_KEY

# Python 3.12 environment the Firebase CLI uses to read the functions
python3.12 -m venv functions/venv && functions/venv/bin/pip install -r functions/requirements.txt

firebase deploy
```

Open `https://YOUR_PROJECT_ID.web.app`. If the first deploy fails on functions with a
permissions or "Eventarc" message, wait 2–3 minutes and run `firebase deploy --only functions`
again; new projects need a moment for permissions to spread.

## Deploy from GitHub Actions (repeatable)

One-time setup:

1. **Create a Firebase project** at <https://console.firebase.google.com> and switch it to the
   **Blaze** (pay-as-you-go) plan. Cloud Functions and Secret Manager need it. Set a budget
   alert in Google Cloud Billing.
2. In the project:
   - **Authentication → Sign-in method → Google**: enable it.
   - **Firestore Database**: create it in production mode.
   - **Storage**: create the default bucket.
   - **Project settings → Your apps → Add app → Web**: copy the config values.
3. **Deploy service account**: Google Cloud console → IAM & Admin → Service Accounts →
   create one. Give it the roles *Firebase Admin*, *Cloud Functions Admin*, *Cloud Run Admin*,
   *Service Account User*, *Secret Manager Admin*, *Cloud Build Editor* and *Artifact
   Registry Administrator*. Then Keys → Add key → JSON.
4. In this GitHub repo → Settings → Secrets and variables → Actions:
   - Secret `FIREBASE_SERVICE_ACCOUNT`: the whole JSON key.
   - Variables `FIREBASE_PROJECT_ID`, `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`,
     `FIREBASE_STORAGE_BUCKET`, `FIREBASE_APP_ID`: from the web app config. These aren't
     secret; they ship in the web page.
   - Variable `ALLOWED_EMAILS`: comma-separated emails allowed to make songs. Optional:
     `DAILY_USD`.
   - Optional: under **Environments → production**, add yourself as a required reviewer.
5. Actions → **Deploy to Firebase** → Run workflow. Tick **update_gemini_secret** the first
   time, so your `GEMINI_API_KEY` is copied into Firebase Secret Manager.

The site is then live at `https://<project-id>.web.app`.

> The deploy workflow hasn't been run yet. The role list in step 3 is a best guess at the
> minimum; if a deploy fails with a permission error, the log names the missing role.
