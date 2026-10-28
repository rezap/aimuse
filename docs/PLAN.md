# AI Muse — Research & Product Plan

> Status: **draft for discussion** (2026‑10‑28). No tech stack is locked in yet;
> section 5 makes a recommendation and lists the alternatives.

## 1. Vision

AI Muse is a personal music muse. It learns what a user likes and turns that
into **custom, consistent, downloadable tracks** without making the user write
prompts.

Four product pillars, in order of importance:

| Pillar | What it means for the user |
|---|---|
| **No prompt barrier** | Pick, swipe, compare and nudge. Text is optional. |
| **Adjusts to taste** | Every like, skip, A/B pick and reference track refines a persistent taste profile. |
| **Consistency** | Tracks in a project (a podcast, a game, a channel, an album) sound like they belong together. |
| **Quality & reuse** | Clean, loudness‑matched files, loops and stems with metadata and a license manifest. You can regenerate any track from its recipe. |

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

Takeaway: hosted APIs give quality and zero ops today. Self‑hosted ACE‑Step +
LoRA is the eventual "your own sound" differentiator.

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
  - **Audio embeddings** (Gemini Embedding 2 hosted, or CLAP / MERT
    self‑hosted): a vector per track to build a taste centroid and measure
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
7. **Later:** ACE‑Step LoRA trained on the user's *own accepted generations*
   gives the strongest consistency and keeps clear ownership.

### 4.4 Quality, download and reuse

- **Automatic QA:** clipping, silence, abrupt endings, duration, spec match,
  and an optional Gemini "listening judge" score.
- **Exports:** WAV/MP3/FLAC, plus loop versions (seamless crossfade at bar
  boundaries), stems via Demucs separation (vocals/drums/bass/other), and
  short/long cuts (15 s / 30 s / 60 s).
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
- The audio tooling (librosa, Essentia, CLAP, Demucs, pyloudnorm) is
  overwhelmingly **Python**, which matches the existing `.gitignore`.
- One backend serves web, Android and any future client.

### 5.2 Proposed stack

| Layer | Recommendation | Alternatives |
|---|---|---|
| Core engine library | **Python 3.12+**, `google-genai`, pydantic | — |
| API | **FastAPI** + async job queue (Arq/RQ on Redis, or Cloud Tasks) | Django, Litestar |
| Storage | **Postgres + pgvector** (SQLite for local dev); object storage on **GCS** (S3 compatible) | Firestore + Vertex Vector Search |
| Audio processing | librosa, Essentia, pyloudnorm, ffmpeg, Demucs, LAION‑CLAP | MERT embeddings |
| Prototype UI | **Gradio** (days, not weeks) | Streamlit |
| Product client v1 | **Web PWA** (SvelteKit or Next.js). Installable on Android and fast to iterate. | Flutter (web + Android from one codebase) |
| Native Android (later) | **Kotlin + Jetpack Compose + Media3/ExoPlayer**, offline library, background playback | Flutter, Kotlin Multiplatform (adds iOS) |
| Hosting | **Cloud Run** (same cloud as Gemini; scale to zero) + GPU worker later for ACE‑Step | Fly.io, Modal (GPU) |
| Auth | Firebase Auth / Google Sign‑In | Supabase |

The client decision between a PWA first and a Flutter app first is the main
open question (section 9).

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
  Next: `ElevenLabsMusicEngine`, `StableAudioEngine`, `AceStepEngine` (self‑hosted).
- The LLM layer (prompt compiler, analysis) gets the same treatment, so it is
  not tied to Gemini either.

### 5.4 Proposed repo layout (when coding starts)

```
aimuse/
  core/        # taste profile, style bible, prompt compiler, ranker, QA (pure Python)
  engines/     # lyria/, lyria_realtime/, elevenlabs/, ace_step/ …
  analysis/    # descriptors, DSP features, embeddings
  api/         # FastAPI app + job workers
  apps/
    prototype/ # Gradio
    web/       # PWA
    android/   # later
  docs/
```

---

## 6. Roadmap

| Phase | Goal | Deliverables | Exit criteria |
|---|---|---|---|
| **0. Spike** (≈1 wk) | Prove Lyria 3.5 quality and consistency tricks | Python CLI on `lyria-3.5` (Interactions API) that does generate → analyze → loudness‑normalize. Experiments: same Style Bible ×10 tracks, with vs without anchor image. | Measured consistency (embedding similarity, BPM/key adherence) and cost per accepted track |
| **1. Core + prototype** (2–3 wks) | Validate the muse loop end‑to‑end | `core/`, `engines/lyria`, `analysis/`. Gradio app: taste quiz, reference upload, one project with a Style Bible, nudges, N‑candidate ranking, downloads with recipe. | 5–10 test users accept ≥1 in 3 tracks without writing a prompt |
| **2. Backend + web app** (4–6 wks) | A real product | FastAPI, jobs, Postgres/pgvector, GCS, auth, PWA, libraries/projects, exports (loops, stems, cuts), budget/quotas | Stable on Cloud Run with cost dashboards |
| **3. Live jam & Android** | Mobile‑native experience | Lyria RealTime jam mode, then native Android (or Flutter), offline library | Play‑store internal test |
| **Lyria 4 upgrade** (when it reaches the Gemini API) | Newest Google model | `LyriaEngine` adapter for Lyria 4 behind a flag; rerun the Phase 0 consistency benchmark on it; switch the default once it wins | Lyria 4 matches or beats 3.5 on consistency and acceptance at acceptable cost |
| **4. Multi‑engine & personal models** | Better quality and ownership | ElevenLabs/Stable Audio adapters, engine routing by task, ACE‑Step + per‑user LoRA on a GPU worker | A/B: personal LoRA beats base for consistency |

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
| No audio conditioning or editing in Lyria | Style Bible + anchor image + N‑best ranking; ACE‑Step later |
| Cost runaway from rerolls and candidates | Per‑user budgets, cached quiz clips, Clip model for drafts and Pro/3.5 for finals |
| Copyright and imitation | Descriptor‑only references, no artist names in prompts, SynthID retained, terms reviewed before launch |
| Commercial‑use ambiguity | Show the license manifest per track; get a legal review before monetizing |
| Spotify API limits | Treat as optional metadata; audio analysis is the primary signal |
| Latency (tens of seconds) | Async jobs + notifications; RealTime for instant feedback |

## 9. Open questions for you

1. **Primary first client:** a web PWA (fastest, works on Android) or go
   straight to Android (native Kotlin or Flutter)?
2. **Target users and use cases:** personal listening, creators needing
   background music (YouTube, podcasts, games), or musicians looking for
   ideas? This changes the defaults (instrumental vs vocals, loops vs songs).
3. **Vocals and lyrics:** day‑one feature, or instrumentals first?
4. **Monetization and licensing:** will users publish tracks commercially?
   That decides how much legal review comes before launch.
5. **Cloud:** OK to standardize on Google Cloud (Cloud Run + GCS) next to
   Gemini?
6. **Self‑hosting appetite:** is a GPU worker for ACE‑Step in scope later, or
   should we stay API‑only?

## 10. Sources

- Google: [Lyria 3.5 in Gemini](https://blog.google/innovation-and-ai/products/gemini-app/better-tracks-lyria-gemini/), [Lyria 3 for developers](https://blog.google/innovation-and-ai/technology/developers-tools/lyria-3-developers/), [Music generation docs](https://ai.google.dev/gemini-api/docs/music-generation), [Lyria 3.5 model page](https://ai.google.dev/gemini-api/docs/models/lyria-3.5), [Lyria RealTime docs](https://ai.google.dev/gemini-api/docs/realtime-music-generation), [Lyria prompt guide](https://ai.google.dev/gemini-api/docs/lyria-prompt-guide)
- Coverage: [Unite.AI](https://www.unite.ai/google-brings-lyria-3-5-music-generation-to-the-gemini-app-and-api/), [The Decoder](https://the-decoder.com/google-brings-ai-music-generation-directly-into-the-gemini-app-with-its-new-lyria-3-5-model/), [invideo Lyria guide](https://invideo.io/blog/lyria-ai-music-generator/), [aicybr Lyria 3.5 guide](https://aicybr.com/blog/google-lyria-3-5-gemini-api-guide), [benchlm Lyria pricing](https://benchlm.ai/md/media-pricing/lyria.md), [Lyria RealTime dev guide](https://dev.to/googleai/lyria-realtime-the-developers-guide-to-infinite-music-streaming-4m1h)
- Alternatives: [AI music API comparison 2026](https://musicapi.ai/blog/best-ai-music-api-2026), [Suno/Udio/ElevenLabs compared](https://www.digitalapplied.com/blog/ai-music-generation-platforms-suno-udio-elevenlabs-2026), [ACE‑Step 1.5](https://github.com/ACE-Step/ACE-Step-1.5), [ACE‑Step paper](https://arxiv.org/abs/2602.00744)
- Spotify API changes: [tunelab summary](https://tunelab-developers.pages.dev/blog/spotify-api-changes-2026), [Spotify community thread](https://community.spotify.com/t5/Spotify-for-Developers/Changes-to-Web-API/td-p/6540414/page/20)
