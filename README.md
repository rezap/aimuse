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

Status: the web app MVP is working: sign in, pick a station and mood, get a song, then play,
download and rate it. It is tested end to end on the Firebase emulators and not yet deployed.
