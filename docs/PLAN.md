# AI Muse — Research & Product Plan

> Status: **plan agreed** (2026‑10‑28). The owner's decisions are in section 9;
> the rest of the plan has been updated to match them.

## 1. Vision

AI Muse is a personal music muse. It learns what a user likes and turns that
into **custom, consistent, downloadable tracks** without making the user write
prompts.

Four product pillars, in order of importance:

| Pillar | What it means for the user |
|---|---|
| **No prompt barrier** | Pick, swipe, compare and nudge. Text is optional. |
| **Adjusts to taste** | Every like, skip, A/B pick and reference track refines a persistent taste profile. |
| **Consistency** | Tracks in a station or album (e.g. "rainy‑morning indie", "gym mix") sound like they belong together. |
| **Quality & reuse** | Clean, loudness‑matched songs you can download and replay, with metadata and a license note. You can regenerate any track from its recipe. |

**First audience: personal listening.** Users get full songs with vocals and
AI‑written lyrics (instrumental is one tap away), organised into personal
stations and albums. Creator features (loops, stems, licensing) come later.

Gemini (Lyria) is the first engine. The architecture keeps engines swappable.

---

## 2. Research findings (October 2026)

> Section 2.1 was checked against Google's official Gemini API docs (model
> pages, music generation guide, Lyria RealTime guide, pricing, changelog) on
> 2026‑10‑28. Items still marked *(verify)* were not covered there.

### 2.1 Google music models available through the Gemini API

| Model | ID | Status | Use | Output | Price* |
|---|---|---|---|---|---|
| **Lyria 3.5** | `lyria-3.5` | Stable / GA since 2026‑09‑03 | Full songs with verses, choruses and bridges, vocals and lyrics; "a couple of minutes", length set in the prompt | 44.1 kHz stereo, MP3 by default, WAV via `response_format`; lyrics and structure as text | $0.08 / song |
| **Lyria 3 Clip** | `lyria-3-clip-preview` | Preview (legacy family) | Always 30 s: clips, loops, previews | 44.1 kHz stereo MP3 | $0.04 / clip |
| Lyria 3 Pro | `lyria-3-pro-preview` | Preview (legacy, superseded by 3.5) | Full songs | 44.1 kHz stereo MP3 | $0.08 / song |
| **Lyria RealTime** | `lyria-realtime-exp` | Experimental | Live, continuous, steerable **instrumental** stream over WebSocket | Raw 16‑bit PCM, 48 kHz stereo, ≤2 s control latency | not listed *(verify)* |

\*Billed per generated song, not per token or second. There is no free tier.
On the paid tier, inputs and outputs are not used to improve Google's products.

Key capabilities and constraints:

- **Inputs:** text, plus up to **10 images** per request. Lyria 3.5 accepts
  **no audio input**, so it can't take a reference track or continue one.
- **Single‑turn:** you cannot edit a generated song iteratively. Every change
  is a new generation, so consistency has to come from our side (section 4.3).
- **Control through the prompt:** tempo, key, mood and instrumentation are
  plain prompt text. Structure uses section tags (`[Verse 1]`, `[Chorus]`,
  `[Bridge]`) or **timestamps** (`[0:00 - 0:10] Intro: …`), which also set the
  length. "Instrumental only, no vocals" switches off vocals. Lyria 3.5 has no
  typed parameters and no seed.
- **Safety filters** block prompts that ask for a specific artist's voice or
  for copyrighted lyrics. Our prompt compiler must never name artists.
- **APIs:** the **Interactions API** (`client.interactions.create`, REST
  `v1beta/interactions`) is recommended. `generate_content` is legacy but still
  supported. Python SDK: `google-genai`. Batch, Flex and Priority inference are
  not supported for Lyria 3.5.
- **SynthID:** every output carries an inaudible AI watermark.
- **Lyria RealTime controls:** weighted prompt blending, `bpm` 60–200,
  `density` 0–1, `brightness` 0–1, `scale` (12 key/mode pairs), `guidance` 0–6
  (default 4), `mute_bass`, `mute_drums`, `only_bass_and_drums`,
  `music_generation_mode` (QUALITY, DIVERSITY or VOCALIZATION), `temperature`
  0–3, `top_k` 1–1000 and `seed`. BPM and scale only change after
  `reset_context()`. The other settings change live. This makes it ideal for
  **taste exploration**, not for final renders.
- **Commercial terms:** these appear to fall under the general Gemini API terms
  rather than a music‑specific license. Copyright protection for AI output is
  limited. *(verify before launch; this matters for the "reusable" promise)*
- **Lyria 4:** not yet listed in the Gemini API docs, model list or changelog
  as of 2026‑10‑28. It goes on the roadmap (section 6) and will plug in as a
  new engine adapter.
- **Gemini Embedding 2** (`gemini-embedding-2`) embeds text, images and
  **audio** into one vector space (audio input ~$0.00016/s). It is a hosted
  alternative to CLAP for taste and consistency embeddings (section 2.3).

### 2.2 Alternative and future engines

| Engine | Strengths | Notes |
|---|---|---|
| **ElevenLabs Music** | Official API, licensed training data, section‑level direction, vocals | ~$0.15/min |
| **Stable Audio 2.5 / 3** | Instrumentals, sound design, long durations (up to 6 min) | Has open‑weights variants |
| **Suno** | Best‑in‑class vocal songs | API access is murky (mostly third‑party wrappers). Avoid at first. |
| **ACE‑Step 1.5 / 1.5 XL** (open source, MIT) | Self‑hostable, fast (<4 GB VRAM claimed), **LoRA fine‑tuning on ~8 songs** | The strongest long‑term path to a truly *personal* style |

Takeaway: hosted APIs give quality and zero ops. **Decision: AI Muse stays
API‑only** (no self‑hosted models or GPUs). ACE‑Step is listed for reference
only. Engines we may add later are hosted ones: Lyria 4, ElevenLabs Music,
Stable Audio.

### 2.3 Analyzing a user's existing interests

- **Spotify:** `audio-features` and `recommendations` return 403 for apps
  created after Nov 2024. Development mode is capped at 5 users (Feb 2026).
  Spotify is now usable only for *metadata* (top artists/tracks/genres), not
  for audio descriptors.
- **Better approach: analyze the audio ourselves.**
  - **Gemini audio understanding** (a Flash‑class model): describe an uploaded
    track as structured tags (genre, sub‑genre, instruments, mood, energy,
    tempo, vocal style, production era, mix character).
  - **DSP features** (librosa / Essentia): BPM, key, loudness, spectral
    brightness, dynamics. These are deterministic and cheap.
  - **Audio embeddings** (Gemini Embedding 2): a vector per track to build a taste centroid and measure
    similarity and consistency.
- **Other signals:** Last.fm / YouTube Music history (metadata), and, most
  valuable of all, **in‑app behavior** on generated clips.
- **Legal guardrail:** reference tracks are used only to *derive descriptors*.
  They are never passed to a generator as audio, and prompts never name
  artists (Lyria likely filters artist names anyway, and it avoids imitation
  claims).

---

## 3. Core concepts

```
 Signals ──► Taste Profile ──► Style Bible (per project) ──► Prompt Compiler ──► Engine ──► Candidates
   ▲                                                                                          │
   └────────────── feedback (pick / like / skip / tweak) ◄── Ranker + QA ◄────────────────────┘
```

- **Taste Profile** (per user): weighted attributes (genres, moods,
  instruments, tempo range, energy, vocals yes/no, language), plus an embedding
  centroid of liked audio and a negative set. It is updated continuously.
- **Style Bible** (per project/collection): a frozen, versioned "sound DNA"
  that holds a canonical style paragraph, BPM and key ranges, instrumentation,
  structure template, mix notes, and an **anchor image**. Every track in the
  project is generated from it. This is the main consistency mechanism.
- **Prompt Compiler:** an LLM (Gemini Flash) turns profile + Style Bible + user
  intent ("calmer", "for a rainy intro", a photo) into an engine‑specific
  prompt. It follows a per‑engine prompt guide and keeps vocabulary stable.
- **Recipe:** everything needed to reproduce a track: engine, model version,
  compiled prompt, inputs, Style Bible version, seed if any, and post‑processing
  steps.

---

## 4. How we deliver each pillar

### 4.1 Removing the prompt barrier

1. **Onboarding taste quiz.** Instead of a questionnaire, show quick A/B pairs
   of 30 s Lyria 3 Clip samples (~$0.04 each, cacheable and shared across
   users). A short series of picks (Bradley–Terry / Elo over attributes) gives
   a usable starting profile.
2. **"Bring your music."** Upload a few tracks or connect Spotify/Last.fm. We
   extract descriptors and propose a profile the user can edit as chips.
3. **Intent without words:** pick a **use case** (focus, workout, intro,
   game level, bedtime…), a **mood** wheel, an **energy** slider, or a
   **photo** (Lyria accepts images natively).
4. **Nudges instead of rewrites:** "more energetic", "less busy", "warmer",
   "drop the vocals". Each one maps to a prompt delta, not to a new prompt.
5. **Live jam mode** (Lyria RealTime): sliders for density, brightness, BPM and
   genre blend. You hear changes as you move them. When you like it, we
   "capture" the settings into a Style Bible for full renders.
6. Power users can always open and edit the compiled prompt.

### 4.2 Adjusting to taste

- Explicit signals: like/dislike, A/B picks, nudges, saving to projects.
- Implicit signals: listen‑through rate, skips, replays, downloads.
- The profile updates attribute weights and the embedding centroid.
  Dislikes feed a negative set used by the ranker. Prompts get phrases to
  avoid only where the engine supports them.
- Taste drift: recent signals weigh more, and the user can view and reset
  the profile.

### 4.3 Consistency

Lyria can't continue or edit a track, so consistency is engineered:

1. **Style Bible text reuse:** identical canonical style wording for every
   track in a project. Only the intent delta changes.
2. **Anchor image:** the same mood‑board image is attached to every
   generation in a project. It is a cheap, native conditioning signal.
3. **Musical constraints:** a fixed key/scale family and BPM band, plus a
   structure template.
4. **Generate N, keep the closest:** render 2–4 candidates, score them by
   embedding similarity to the project centroid, and auto‑reject outliers.
5. **Verify, then reroll:** detect BPM/key/duration. If a track is off‑spec,
   reroll it automatically (with a budget cap).
6. **Post‑processing:** LUFS loudness normalization (e.g. ‑14 LUFS streaming
   or ‑16 podcast), true‑peak limiting, fades, and bar‑aligned trimming for
   loops.

### 4.4 Quality, download and reuse

- **Automatic QA:** clipping, silence, abrupt endings, duration, spec match,
  and an optional Gemini "listening judge" score.
- **Exports (launch):** MP3 and WAV downloads, lyrics, cover art, and offline
  playback in the web app.
- **Exports (later, for creators):** loop versions (seamless crossfade at bar
  boundaries), stems via Demucs separation, and 15/30/60 s cuts.
- **Metadata:** ID3/BWF tags (BPM, key, LUFS, project) and a sidecar
  `recipe.json`, plus a **license manifest** (engine, terms version, SynthID
  note, date).
- **Libraries:** projects/collections, search by mood/BPM/key, and
  "regenerate a variation" from any recipe.

---

## 5. Architecture & tech stack (recommendation)

### 5.1 Why backend‑first

- API keys and billing must never ship inside a mobile app.
- Generation takes tens of seconds and needs **async jobs**, retries and
  budget caps.
- The audio tooling (librosa, Essentia, pyloudnorm) is overwhelmingly
  **Python**, which matches the existing `.gitignore`.
- One backend serves web, Android and any future client.

### 5.2 Stack (decided: web app first, on Firebase)

| Layer | Choice | Notes |
|---|---|---|
| Web client | **Next.js PWA, static export on Firebase Hosting** (simpler and cheaper than App Hosting; no server needed) | Installable on Android; player‑first UI for personal listening; offline cache of downloaded songs |
| Auth | **Firebase Auth** (Google Sign‑In) | Same accounts later for an Android app |
| Database | **Cloud Firestore** | Users, taste profiles, stations, tracks, recipes, jobs. Firestore vector search holds track and taste embeddings. |
| Files | **Cloud Storage for Firebase** | Generated audio, cover art, user‑uploaded reference tracks (private per user) |
| Generation & analysis | **Python 3.12 on Cloud Functions for Firebase (2nd gen, runs on Cloud Run)** | Triggered by a Firestore job document; calls Lyria and Gemini, analyses and normalises audio, writes results back. Clients never hold the Gemini API key. |
| Core library | **Python**: `google-genai`, pydantic, librosa, pyloudnorm, ffmpeg | Shared by the functions and a local CLI |
| Embeddings | **Gemini Embedding 2** (hosted, audio + text) | No self‑hosted models (API‑only decision) |
| Prototype / dev tools | Python CLI (+ optional Gradio) | For the Phase 0 spike only |
| Android (later) | Kotlin + Jetpack Compose + Media3, same Firebase backend | After the web app proves the loop |

### 5.3 Provider abstraction (pluggable engines)

```python
class MusicEngine(Protocol):
    id: str
    capabilities: EngineCapabilities   # max_duration, vocals, lyrics, image_input,
                                       # audio_input, realtime, seed, formats, cost
    def compile(self, req: GenerationRequest) -> EnginePrompt: ...   # engine-specific prompt dialect
    async def generate(self, prompt: EnginePrompt, n: int) -> list[AudioAsset]: ...

class AnalysisModel(Protocol):          # Gemini audio understanding today, swappable
    async def describe(self, audio: AudioAsset) -> TrackDescriptors: ...
```

- The **Taste Profile, Style Bible, ranker and QA are engine‑agnostic.** Only
  `compile()` knows an engine's prompt dialect.
- Initial adapters: `LyriaEngine` (3.5 + Clip) and `LyriaRealtimeSession`.
  Next: Lyria 4 when it lands, then optionally `ElevenLabsMusicEngine` and
  `StableAudioEngine` (all hosted APIs).
- The LLM layer (prompt compiler, analysis) gets the same treatment, so it is
  not tied to Gemini either.

### 5.4 Repo layout

```
aimuse/
  backend/            # Python package `aimuse`: models, prompt compiler, engines,
    src/aimuse/       # analysis, pipeline, spike experiment, CLI, station presets
    tests/            # offline tests (fake engine, mocked Lyria API)
  functions/          # Cloud Functions for Firebase (Python): song jobs, wraps backend/
  web/                # Next.js PWA: sign in, composer, live progress, library
  scripts/            # dev.sh (local emulators), e2e.sh (end-to-end test)
  android/            # later
  .github/workflows/  # backend-ci, app-ci (every push); lyria-spike, deploy (manual)
  docs/
```

---

## 6. Roadmap

| Phase | Goal | Deliverables | Exit criteria |
|---|---|---|---|
| **0. Spike** (≈1 wk) | Prove Lyria 3.5 quality and consistency tricks | Python CLI on `lyria-3.5` (Interactions API) that does generate → analyze → loudness‑normalize. Experiments: same Style Bible ×10 tracks, with vs without anchor image. | Measured consistency (embedding similarity, BPM/key adherence) and cost per accepted track |
| **1. Core + Firebase backend** (2–3 wks) | The muse loop running in the cloud | `core/`, `engines/lyria`, `analysis/`, Python Cloud Functions job pipeline, Firestore schema + security rules, Storage, budgets | A track request from a test client produces a ranked, normalised song with lyrics and recipe |
| **2. Web app MVP** (4–6 wks) | A real product for personal listening | Next.js PWA: sign‑in, taste quiz, reference upload, stations/albums with Style Bibles, player, nudges, likes/skips feedback, downloads | 5–10 test users accept ≥1 in 3 tracks without writing a prompt |
| **3. Live jam & Android** | Mobile‑native experience | Lyria RealTime jam mode, then a native Android app on the same Firebase backend | Play‑store internal test |
| **Creator features** (if the audience widens) | Reuse in videos, podcasts, games | Loops, stems, cuts, licensing decision (section 9) | Legal review done |
| **Lyria 4 upgrade** (when it reaches the Gemini API) | Newest Google model | `LyriaEngine` adapter for Lyria 4 behind a flag; rerun the Phase 0 consistency benchmark on it; switch the default once it wins | Lyria 4 matches or beats 3.5 on consistency and acceptance at acceptable cost |
| **4. More hosted engines** (optional) | Better quality per task | ElevenLabs/Stable Audio adapters and engine routing by task | An engine wins A/B tests on acceptance or cost |

## 7. Metrics

- **Acceptance rate:** downloaded or saved ÷ generated.
- **Cost per accepted track.**
- **Consistency score:** mean pairwise embedding similarity within a project;
  BPM/key adherence %.
- **Prompt‑free rate:** share of tracks created without typed text.
- Time to first liked track; reroll rate; listen‑through rate.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Preview models change, get renamed or are retired | Engine adapters, versioned recipes, contract tests per engine |
| No audio conditioning or editing in Lyria | Style Bible + anchor image + N‑best ranking; re‑evaluate with Lyria 4 |
| Cost runaway from rerolls and candidates | Per‑user budgets, cached quiz clips, Clip model ($0.04) for drafts and previews, Lyria 3.5 ($0.08) for finals |
| Copyright and imitation | Descriptor‑only references, no artist names in prompts, SynthID retained, terms reviewed before launch |
| Commercial‑use ambiguity | Show the license manifest per track; get a legal review before monetizing |
| Spotify API limits | Treat as optional metadata; audio analysis is the primary signal |
| Latency (tens of seconds) | Async jobs + notifications; RealTime for instant feedback |

## 9. Decisions (2026‑10‑28)

| # | Question | Decision |
|---|---|---|
| 1 | First app | **Web app (PWA)** first; native Android later |
| 2 | First audience | **Personal listening** |
| 3 | Vocals and lyrics | **Vocals with AI‑written lyrics** by default; instrumental as an option |
| 4 | Commercial use of tracks | **Not decided.** Keep a per‑track license note and decide before public launch (legal review of Google's terms). |
| 5 | Hosting | **Firebase** (App Hosting, Auth, Firestore, Storage, Python Cloud Functions) |
| 6 | Own models on GPUs | **No — API‑only for good.** Hosted engines only. |
| — | Music model | **Start with Lyria 3.5**; add **Lyria 4** as soon as it is in the Gemini API |

## 10. Sources

- Google: [Lyria 3.5 in Gemini](https://blog.google/innovation-and-ai/products/gemini-app/better-tracks-lyria-gemini/), [Lyria 3 for developers](https://blog.google/innovation-and-ai/technology/developers-tools/lyria-3-developers/), [Music generation docs](https://ai.google.dev/gemini-api/docs/music-generation), [Lyria 3.5 model page](https://ai.google.dev/gemini-api/docs/models/lyria-3.5), [Lyria RealTime docs](https://ai.google.dev/gemini-api/docs/realtime-music-generation), [Lyria prompt guide](https://ai.google.dev/gemini-api/docs/lyria-prompt-guide)
- Coverage: [Unite.AI](https://www.unite.ai/google-brings-lyria-3-5-music-generation-to-the-gemini-app-and-api/), [The Decoder](https://the-decoder.com/google-brings-ai-music-generation-directly-into-the-gemini-app-with-its-new-lyria-3-5-model/), [invideo Lyria guide](https://invideo.io/blog/lyria-ai-music-generator/), [aicybr Lyria 3.5 guide](https://aicybr.com/blog/google-lyria-3-5-gemini-api-guide), [benchlm Lyria pricing](https://benchlm.ai/md/media-pricing/lyria.md), [Lyria RealTime dev guide](https://dev.to/googleai/lyria-realtime-the-developers-guide-to-infinite-music-streaming-4m1h)
- Alternatives: [AI music API comparison 2026](https://musicapi.ai/blog/best-ai-music-api-2026), [Suno/Udio/ElevenLabs compared](https://www.digitalapplied.com/blog/ai-music-generation-platforms-suno-udio-elevenlabs-2026), [ACE‑Step 1.5](https://github.com/ACE-Step/ACE-Step-1.5), [ACE‑Step paper](https://arxiv.org/abs/2602.00744)
- Spotify API changes: [tunelab summary](https://tunelab-developers.pages.dev/blog/spotify-api-changes-2026), [Spotify community thread](https://community.spotify.com/t5/Spotify-for-Developers/Changes-to-Web-API/td-p/6540414/page/20)
