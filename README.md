# aimuse
Use agentic AI to create your music for you to listen to from today to your end 

AI Muse learns your musical taste and generates custom, consistent,
downloadable tracks without making you write prompts. It starts with Google's
Lyria models through the Gemini API and keeps the engine layer pluggable.

- 📄 **[Research & product plan](docs/PLAN.md)** covers the vision, model
  research, architecture, roadmap and decisions.
- 🎛️ **[Backend core](backend/README.md)** is the Python package that compiles
  prompts, calls Lyria, analyses and ranks tracks. Its tests run on GitHub
  Actions, and a manually started workflow runs paid Lyria experiments.

Status: Phase 0. The core backend and the Lyria experiment are in place.
