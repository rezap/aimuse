"use client";

import { collection, deleteDoc, doc, onSnapshot, orderBy, query, updateDoc } from "firebase/firestore";
import { deleteObject, getDownloadURL, ref } from "firebase/storage";
import { useEffect, useState } from "react";

import { db, storage } from "@/lib/firebase";
import { formatDuration, gradient, stations } from "@/lib/music";
import type { Track } from "@/lib/types";

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
  }

  const ext = track.mimeType === "audio/wav" ? "wav" : "mp3";
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
            {track.vocals && track.vocalsDelivered === false ? " · came out instrumental" : ""}
          </span>
        </div>
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
        {track.lyrics && (
          <details>
            <summary>Lyrics</summary>
            <pre>{track.lyrics}</pre>
          </details>
        )}
      </div>
    </li>
  );
}
