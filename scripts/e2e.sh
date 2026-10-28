#!/usr/bin/env bash
# Start the emulators (fake engine) and the web app, run web/tests/e2e.mjs, shut down.
# Used by CI; also handy locally. Screenshots go to $SHOTS_DIR when set.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x functions/venv/bin/python ]; then
  "$(command -v python3.12 || command -v python3)" -m venv functions/venv
  functions/venv/bin/pip install -q -r functions/requirements.txt
fi
rm -rf functions/aimuse && cp -r backend/src/aimuse functions/aimuse
printf 'AIMUSE_ENGINE=fake\nAIMUSE_DAILY_USD=5\n' > functions/.env.local
[ -f functions/.secret.local ] || printf 'GEMINI_API_KEY=not-needed-for-fake-engine\n' > functions/.secret.local

# Production build of the web app, pointed at the emulators, served as static files.
[ -d web/node_modules ] || npm --prefix web ci
NEXT_PUBLIC_USE_EMULATORS=1 npm --prefix web run build

FIREBASE="${FIREBASE:-npx --yes firebase-tools@15.34.1}"
$FIREBASE emulators:exec --project demo-aimuse --only auth,firestore,storage,functions \
  'python3 -m http.server 3000 --bind 127.0.0.1 -d web/out >/dev/null 2>&1 & WEB=$!
   for i in $(seq 1 30); do curl -sf http://localhost:3000 >/dev/null && break; sleep 1; done
   node web/tests/e2e.mjs; code=$?; kill $WEB; exit $code'
