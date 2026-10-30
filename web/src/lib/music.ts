import { addDoc, collection, serverTimestamp } from "firebase/firestore";

import { db } from "./firebase";
import stationsJson from "./stations.json";
import type { Station } from "./types";

export const stations = stationsJson as Station[];

export const MOODS = [
  "calm",
  "cosy",
  "dreamy",
  "hopeful",
  "nostalgic",
  "melancholic",
  "focused",
  "uplifting",
  "euphoric",
] as const;

export type SongRequest = {
  stationId: string;
  mood: string | null;
  theme: string | null;
  energy: number | null;
  vocals: boolean | null;
  inspiration?: string | null;
};

/** Queue a song. The Cloud Function picks the job up and writes the track when it's ready. */
export async function requestSong(uid: string, req: SongRequest): Promise<string> {
  const theme = req.theme?.trim() ? req.theme.trim().slice(0, 200) : null;
  const ref = await addDoc(collection(db, "users", uid, "jobs"), {
    stationId: req.stationId,
    mood: req.mood,
    theme,
    energy: req.energy,
    inspiration: req.inspiration?.trim() ? req.inspiration.trim().slice(0, 80) : null,
    vocals: req.vocals,
    status: "queued",
    createdAt: serverTimestamp(),
  });
  return ref.id;
}

/** A random but sensible request, for the "Surprise me" button. */
export function surpriseRequest(rand: () => number = Math.random): SongRequest {
  const pick = <T,>(xs: readonly T[]) => xs[Math.floor(rand() * xs.length)];
  const station = pick(stations);
  return {
    stationId: station.id,
    mood: pick(station.moods.length ? station.moods : MOODS),
    theme: station.ideas.length ? pick(station.ideas) : null,
    energy: Math.round(rand() * 10) / 10,
    vocals: null,
  };
}

export function formatDuration(s: number | null): string {
  if (s == null) return "–";
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.round(s % 60)).padStart(2, "0")}`;
}

export function gradient(palette: string[]): string {
  const cols = palette.length ? palette : ["#334", "#667"];
  return `linear-gradient(135deg, ${cols.join(", ")})`;
}
