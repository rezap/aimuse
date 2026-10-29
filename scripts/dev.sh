#!/usr/bin/env bash
# Run the whole app locally on the Firebase emulators. No Firebase project or API key needed:
# songs come from the fake engine (synthetic audio). Opens:
#   web app      http://127.0.0.1:3000
#   emulator UI  http://127.0.0.1:4000
# Use AIMUSE_ENGINE=lyria and a real key in functions/.secret.local to hear real songs locally.
set -euo pipefail
cd "$(dirname "$0")/.."

# Python environment for the functions emulator, with the backend package copied in.
if [ ! -x functions/venv/bin/python ]; then
  # Match the deployed runtime (python312 in firebase.json).
  "$(command -v python3.12 || command -v python3)" -m venv functions/venv
  functions/venv/bin/pip install -q -r functions/requirements.txt
fi
rm -rf functions/aimuse && cp -r backend/src/aimuse functions/aimuse
[ -f functions/.env.local ] || printf 'AIMUSE_ENGINE=fake\nAIMUSE_DAILY_USD=5\nAIMUSE_ALLOWED_EMAILS=*\n' > functions/.env.local
[ -f functions/.secret.local ] || printf 'GEMINI_API_KEY=not-needed-for-fake-engine\n' > functions/.secret.local

# Web app pointed at the emulators.
[ -d web/node_modules ] || npm --prefix web ci
export NEXT_PUBLIC_USE_EMULATORS=1

FIREBASE="${FIREBASE:-npx --yes firebase-tools@15.34.1}"
$FIREBASE emulators:exec --project demo-aimuse --only auth,firestore,storage,functions \
  --ui "npm --prefix web run dev -- --port 3000"
