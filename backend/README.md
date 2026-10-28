# AI Muse backend (core)

A Python package (`aimuse`) that turns a **style bible** (a station's "sound DNA") plus a
listener **intent** into finished tracks. It works in these steps:

1. Compile a deterministic prompt, optionally with the station's anchor image.
2. Call the engine. That is Lyria via the Gemini API, or a fake offline engine.
3. Analyse the audio: tempo, key, loudness, clipping, silence, timbre.
4. Check the track against its targets, rank the candidates, and keep the best one.
5. Write the audio, lyrics, a `recipe.json` per track, and a report.

Later, Firebase Cloud Functions and the web app will call this same package.

## Layout

| Path | What |
|---|---|
| `src/aimuse/models.py` | Style bible, intent, targets, keys |
| `src/aimuse/prompt.py`, `anchor.py` | Prompt compiler and anchor image |
| `src/aimuse/engines/` | `LyriaEngine` (REST, Interactions API), `FakeEngine` (offline synth) |
| `src/aimuse/analysis.py` | Decoding, measurements, QA checks, loudness normalisation, consistency |
| `src/aimuse/pipeline.py` | Generate → analyse → rank → recipe, with a hard budget cap |
| `src/aimuse/spike.py` | Phase 0 experiment and its report |
| `src/aimuse/presets/*.json` | Built-in stations. Copy one to make your own. |

## Run it on GitHub (recommended)

- **Backend CI** runs on every push and PR that touches `backend/`. It runs lint, the
  offline tests, and a smoke run with the fake engine. It needs no key and costs nothing.
- **Live API tests (paid, about $0.04)**: go to **Actions → Backend CI → Run workflow**, tick
  **live** (and pick a station). It runs the real pipeline once with `lyria-3-clip-preview`,
  checks the audio, and uploads the clip, lyrics, prompt, recipe and a summary as the run's
  artifact `lyria-live-test-…` so you can listen to it. These tests never run on push or PR. Locally: `AIMUSE_LIVE=1 GEMINI_API_KEY=... pytest -m live`.
- **Lyria spike (paid)** runs only when you start it:
  1. Add your key once: repo **Settings → Secrets and variables → Actions → New repository
     secret**, named `GEMINI_API_KEY`. For an approval step on every run, add the secret to
     the `lyria` environment instead (**Settings → Environments → lyria**) and turn on
     **Required reviewers**.
  2. Go to **Actions → Lyria spike (paid) → Run workflow**. Choose the station, the number of
     tracks, the arms, the model and a **spending cap** (default $1, maximum $20).
  3. When it finishes, the run page shows the report. The audio, lyrics, recipes and
     `report.json` are in the run's **Artifacts** (kept 14 days).

Cost: `lyria-3.5` is $0.08 per request and `lyria-3-clip-preview` is $0.04. The default run
(3 tracks × 2 arms × 1 candidate on `lyria-3.5`) makes 6 requests, about $0.48. The cap is
checked before every request, and failed requests also count against it.

## Run it locally

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest                                   # offline tests
aimuse presets                           # list stations
aimuse prompt --preset late-night-lofi   # see compiled prompts (free)
aimuse spike --engine fake --tracks 2    # full pipeline, synthetic audio (free)
GEMINI_API_KEY=... aimuse spike --tracks 3 --max-cost 1.00   # real Lyria (paid)
aimuse analyze some-song.mp3             # measure any audio file
```
