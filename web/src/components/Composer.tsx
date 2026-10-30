"use client";

import { useState } from "react";

import { gradient, MOODS, requestSong, stations, surpriseRequest, type SongRequest } from "@/lib/music";

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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const station = stations.find((s) => s.id === stationId) ?? stations[0];

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
          We turn this into a musical description (genre, era, instruments, vocal feel). Your
          song is original: the artist&apos;s name, voice, lyrics and songs are never used.
        </p>
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
