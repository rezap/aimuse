"use client";

import { useEffect, useState } from "react";

import {
  gradient,
  MOODS,
  requestSong,
  stations,
  surpriseRequest,
  type Singer,
  type SongRequest,
} from "@/lib/music";
import {
  type ArtistPreview,
  describeArtist,
  loadTweaks,
  NO_TWEAKS,
  saveTweaks,
  TWEAKS,
  type VoiceTweaks,
} from "@/lib/voice";

type Preview =
  | { state: "idle" }
  | { state: "loading"; reference: string }
  | { state: "ready"; reference: string; data: ArtistPreview }
  | { state: "error"; reference: string; message: string };

type Props = { uid: string };

const MAX_LYRICS = 3000;

const ENERGY_LABELS = ["Very calm", "Relaxed", "Steady", "High energy"];

export function Composer({ uid }: Props) {
  const [stationId, setStationId] = useState(stations[0]?.id ?? "");
  const [mood, setMood] = useState<string | null>(null);
  const [energy, setEnergy] = useState(0.5);
  const [theme, setTheme] = useState("");
  const [inspiration, setInspiration] = useState("");
  const [lyricsMode, setLyricsMode] = useState(false);
  const [lyrics, setLyrics] = useState("");
  const [vocals, setVocals] = useState<boolean | null>(null);
  const [singer, setSinger] = useState<Singer | null>(null);
  const [tweaks, setTweaks] = useState<VoiceTweaks>(NO_TWEAKS);
  const [preview, setPreview] = useState<Preview>({ state: "idle" });

  // Preview what the artist reference means (a moment after typing stops), and bring back the
  // voice nudges saved for that artist. The song reuses the same cached description.
  useEffect(() => {
    const reference = inspiration.trim();
    if (!reference) {
      setPreview({ state: "idle" });
      return;
    }
    let alive = true;
    const timer = setTimeout(async () => {
      setPreview({ state: "loading", reference });
      try {
        const data = await describeArtist(reference);
        if (!alive) return;
        setPreview({ state: "ready", reference, data });
        const saved = await loadTweaks(uid, data.key).catch(() => null);
        if (alive) setTweaks(saved ?? NO_TWEAKS);
      } catch (e) {
        const message = e instanceof Error ? e.message : String(e);
        if (alive) setPreview({ state: "error", reference, message });
      }
    }, 900);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [inspiration, uid]);

  function nudge(name: keyof VoiceTweaks, value: number) {
    const next = { ...tweaks, [name]: tweaks[name] === value ? 0 : value };
    setTweaks(next);
    if (preview.state === "ready") saveTweaks(uid, preview.data.key, next).catch(() => undefined);
  }

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const station = stations.find((s) => s.id === stationId) ?? stations[0];
  const sung = lyricsMode || (vocals ?? Boolean(station?.vocals));

  async function submit(req: SongRequest) {
    setBusy(true);
    setError(null);
    try {
      await requestSong(uid, req);
      setTheme("");
      setLyrics("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Make a song</h2>

      <div className="stations" role="radiogroup" aria-label="Station">
        {stations.map((s) => (
          <button
            key={s.id}
            role="radio"
            aria-checked={s.id === stationId}
            className={`station ${s.id === stationId ? "selected" : ""}`}
            style={{ backgroundImage: gradient(s.palette) }}
            onClick={() => setStationId(s.id)}
          >
            <strong>{s.name}</strong>
            <span>{s.genres.join(" · ")}</span>
          </button>
        ))}
      </div>
      {station && <p className="muted">{station.description}</p>}

      <div className="field">
        <label>Mood</label>
        <div className="chips">
          {MOODS.map((m) => (
            <button
              key={m}
              className={`chip ${mood === m ? "on" : ""}`}
              onClick={() => setMood(mood === m ? null : m)}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div className="field">
        <label htmlFor="energy">
          Energy: <span className="muted">{ENERGY_LABELS[Math.min(3, Math.floor(energy * 4))]}</span>
        </label>
        <input
          id="energy"
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={energy}
          onChange={(e) => setEnergy(Number(e.target.value))}
        />
      </div>

      <div className="field">
        <label htmlFor="theme">
          What's it about? <span className="muted">(optional)</span>
        </label>
        <input
          id="theme"
          type="text"
          maxLength={200}
          placeholder={station?.ideas[0] ?? "a quiet morning"}
          value={theme}
          onChange={(e) => setTheme(e.target.value)}
          onPaste={(e) => {
            // A multi-line or long paste is almost certainly lyrics, not a topic: the one-line
            // field would silently drop the line breaks and cut it at 200 characters.
            const text = e.clipboardData.getData("text");
            if (text.includes("\n") || text.length > 200) {
              e.preventDefault();
              setLyrics(text.slice(0, MAX_LYRICS));
              setLyricsMode(true);
            }
          }}
        />
        {station && station.ideas.length > 0 && (
          <div className="chips small">
            {station.ideas.slice(0, 4).map((idea) => (
              <button key={idea} className="chip" onClick={() => setTheme(idea)}>
                {idea}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="field">
        {lyricsMode ? (
          <>
            <label htmlFor="lyrics">
              Your lyrics{" "}
              <span className="muted">
                ({lyrics.length}/{MAX_LYRICS})
              </span>
            </label>
            <textarea
              id="lyrics"
              rows={10}
              maxLength={MAX_LYRICS}
              placeholder={"[Verse]\nWrite your own words here…\n\n[Chorus]\n…"}
              value={lyrics}
              onChange={(e) => setLyrics(e.target.value)}
            />
            <p className="hint muted">
              Sung as written; a blank line starts a new verse. Lyria refuses well-known songs
              and famous poems (even old public-domain ones), so original words work best.
            </p>
            <button className="ghost small" onClick={() => setLyricsMode(false)}>
              Use a topic instead
            </button>
          </>
        ) : (
          <button className="ghost small" onClick={() => setLyricsMode(true)}>
            ✍️ Use my own lyrics
          </button>
        )}
      </div>

      <div className="field">
        <label htmlFor="inspiration">
          In the spirit of… <span className="muted">(optional artist or band)</span>
        </label>
        <input
          id="inspiration"
          type="text"
          maxLength={80}
          placeholder="e.g. Bob Dylan, Daft Punk, 90s Britpop"
          value={inspiration}
          onChange={(e) => setInspiration(e.target.value)}
        />
        <p className="hint muted">
          We turn this into a musical description (genre, era, singer, instruments, tempo,
          production) that leads the song. Your song is original: the artist&apos;s name, voice,
          lyrics and songs are never used. Add a year for a period, e.g. &quot;Bob Dylan 1965&quot;.
        </p>
        {preview.state === "loading" && <p className="hint muted">Describing the style…</p>}
        {preview.state === "error" && (
          <p className="hint error">Couldn&apos;t describe that style: {preview.message}</p>
        )}
        {preview.state === "ready" && (
          <p className="preview" data-testid="artist-preview">
            {preview.data.summary}
          </p>
        )}
      </div>

      <div className="field" hidden={lyricsMode}>
        <label>Vocals</label>
        <div className="chips">
          {[
            { v: null, label: `Station default (${station?.vocals ? "vocals" : "instrumental"})` },
            { v: true, label: "With vocals" },
            { v: false, label: "Instrumental" },
          ].map((o) => (
            <button
              key={String(o.v)}
              className={`chip ${vocals === o.v ? "on" : ""}`}
              onClick={() => setVocals(o.v)}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <div className="field" hidden={!sung}>
        <label>Singer</label>
        <div className="chips">
          {[
            { v: null, label: inspiration.trim() ? "Like the artist" : "Any" },
            { v: "male" as const, label: "Male" },
            { v: "female" as const, label: "Female" },
          ].map((o) => (
            <button
              key={String(o.v)}
              className={`chip ${singer === o.v ? "on" : ""}`}
              onClick={() => setSinger(o.v)}
            >
              {o.label}
            </button>
          ))}
        </div>
        {preview.state === "ready" && preview.data.voice && (
          <p className="preview" data-testid="voice-preview">
            Voice: {preview.data.voice}
          </p>
        )}
        <label className="sub">
          Adjust the voice{" "}
          <span className="muted">
            {preview.state === "ready" ? "(saved for this artist)" : "(optional)"}
          </span>
        </label>
        <div className="chips small tweaks">
          {TWEAKS.map((t) => (
            <span key={t.name} className="pair">
              <button
                className={`chip ${tweaks[t.name] === -1 ? "on" : ""}`}
                aria-pressed={tweaks[t.name] === -1}
                onClick={() => nudge(t.name, -1)}
              >
                {t.down}
              </button>
              <button
                className={`chip ${tweaks[t.name] === 1 ? "on" : ""}`}
                aria-pressed={tweaks[t.name] === 1}
                onClick={() => nudge(t.name, 1)}
              >
                {t.up}
              </button>
            </span>
          ))}
        </div>
      </div>

      <div className="actions">
        <button
          className="primary"
          disabled={busy || !station || (lyricsMode && !lyrics.trim())}
          onClick={() =>
            submit({
              stationId,
              mood,
              theme,
              energy,
              vocals: lyricsMode ? true : vocals,
              singer,
              voiceTweaks: tweaks,
              inspiration,
              lyrics: lyricsMode ? lyrics : null,
            })
          }
        >
          {busy ? "Sending…" : "Make it"}
        </button>
        <button disabled={busy} onClick={() => submit(surpriseRequest())}>
          Surprise me
        </button>
      </div>
      {error && <p className="error">Couldn't start the song: {error}</p>}
    </section>
  );
}
