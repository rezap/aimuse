"use client";

import { collection, deleteDoc, doc, onSnapshot, orderBy, query, updateDoc } from "firebase/firestore";
import { deleteObject, getDownloadURL, ref } from "firebase/storage";
import { useEffect, useState } from "react";

import { db, storage } from "@/lib/firebase";
import { formatLyrics } from "@/lib/lyrics";
import { formatDuration, gradient, stations } from "@/lib/music";
import type { Track } from "@/lib/types";

const SINGER_LABEL = { male: "male voice", female: "female voice", duet: "duet" } as const;

export function Library({ uid }: { uid: string }) {
  const [tracks, setTracks] = useState<Track[] | null>(null);

  useEffect(() => {
    const q = query(collection(db, "users", uid, "tracks"), orderBy("createdAt", "desc"));
    return onSnapshot(q, (snap) =>
      setTracks(snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<Track, "id">) }))),
    );
  }, [uid]);

  return (
    <section className="card">
      <h2>Your songs</h2>
      {tracks === null && <p className="muted">Loading…</p>}
      {tracks?.length === 0 && <p className="muted">No songs yet. Make your first one above.</p>}
      <ul className="tracks">
        {tracks?.map((t) => <TrackCard key={t.id} uid={uid} track={t} />)}
      </ul>
    </section>
  );
}

function TrackCard({ uid, track }: { uid: string; track: Track }) {
  const [url, setUrl] = useState<string | null>(null);
  const palette = stations.find((s) => s.id === track.stationId)?.palette ?? [];
  const trackRef = doc(db, "users", uid, "tracks", track.id);

  useEffect(() => {
    let alive = true;
    getDownloadURL(ref(storage, track.audioPath))
      .then((u) => alive && setUrl(u))
      .catch(() => alive && setUrl(null));
    return () => {
      alive = false;
    };
  }, [track.audioPath]);

  const rate = (r: -1 | 1) => updateDoc(trackRef, { rating: track.rating === r ? 0 : r });

  async function remove() {
    if (!confirm(`Delete "${track.title}"?`)) return;
    await deleteObject(ref(storage, track.audioPath)).catch(() => undefined);
    await deleteDoc(trackRef);
    // The song's job (same id) is no longer needed either.
    await deleteDoc(doc(db, "users", uid, "jobs", track.id)).catch(() => undefined);
  }

  const ext = track.mimeType === "audio/wav" ? "wav" : "mp3";
  const lyrics = formatLyrics(track.lyrics);
  return (
    <li className="track">
      <div className="art" style={{ backgroundImage: gradient(palette) }} aria-hidden />
      <div className="grow">
        <div className="track-head">
          <strong>{track.title}</strong>
          <span className="muted">
            {track.stationName} · {formatDuration(track.durationS)}
            {track.bpm ? ` · ${Math.round(track.bpm)} BPM` : ""}
            {track.vocals ? "" : " · instrumental"}
            {track.vocals && track.singer ? ` · ${SINGER_LABEL[track.singer]}` : ""}
            {track.vocals && track.vocalsDelivered === false ? " · came out instrumental" : ""}
          </span>
        </div>
        {track.inspiration && (
          <p className="influence muted">
            In the spirit of {track.inspiration}
            {track.influences ? ` → ${track.influences}` : ""}
            {track.inspirationNote ? ` · ${track.inspirationNote}` : ""}
          </p>
        )}
        {track.voice && <p className="voice-line muted">Voice: {track.voice}</p>}
        {url ? <audio controls preload="none" src={url} /> : <p className="muted">Loading audio…</p>}
        <div className="track-actions">
          <button
            aria-pressed={track.rating === 1}
            className={track.rating === 1 ? "on" : ""}
            onClick={() => rate(1)}
            title="More like this"
          >
            👍
          </button>
          <button
            aria-pressed={track.rating === -1}
            className={track.rating === -1 ? "on" : ""}
            onClick={() => rate(-1)}
            title="Less like this"
          >
            👎
          </button>
          {url && (
            <a className="button" href={url} download={`${track.title}.${ext}`} target="_blank" rel="noreferrer">
              Download
            </a>
          )}
          <button className="ghost" onClick={remove}>
            Delete
          </button>
        </div>
        {lyrics.length > 0 && (
          <details>
            <summary>Lyrics</summary>
            <div className="lyrics">
              {lyrics.map((section, i) => (
                <p key={i}>
                  {section.heading && <span className="lyric-heading">{section.heading}</span>}
                  {section.lines.map((line, j) => (
                    <span key={j} className="lyric-line">
                      {line}
                    </span>
                  ))}
                </p>
              ))}
            </div>
          </details>
        )}
      </div>
    </li>
  );
}
