import { doc, getDoc, serverTimestamp, setDoc } from "firebase/firestore";
import { httpsCallable } from "firebase/functions";

import { db, functions } from "./firebase";

/** The listener's nudges on top of a voice: -1, 0 or +1 each. */
export type VoiceTweaks = { pitch: number; grit: number; spoken: number; space: number };

export const NO_TWEAKS: VoiceTweaks = { pitch: 0, grit: 0, spoken: 0, space: 0 };

/** Each nudge as a pair of opposite chips: [-1 label, +1 label]. */
export const TWEAKS: { name: keyof VoiceTweaks; down: string; up: string }[] = [
  { name: "pitch", down: "Lower", up: "Higher" },
  { name: "grit", down: "Smoother", up: "Rougher" },
  { name: "spoken", down: "More sung", up: "More spoken" },
  { name: "space", down: "Drier", up: "More reverb" },
];

export const hasTweaks = (t: VoiceTweaks) => Object.values(t).some((v) => v !== 0);

/** What "In the spirit of <artist>" will mean, from the same cached description the song uses. */
export type ArtistPreview = {
  key: string;
  summary: string;
  era: string | null;
  singer: "male" | "female" | "duet" | null;
  voice: string | null;
};

export async function describeArtist(reference: string): Promise<ArtistPreview> {
  const call = httpsCallable<{ reference: string }, ArtistPreview>(functions, "describe_artist");
  return (await call({ reference })).data;
}

/** Voice nudges saved for an artist, so the next song "like X" starts from them. */
export async function loadTweaks(uid: string, key: string): Promise<VoiceTweaks | null> {
  const snap = await getDoc(doc(db, "users", uid, "voices", key));
  return snap.exists() ? { ...NO_TWEAKS, ...(snap.data().tweaks as Partial<VoiceTweaks>) } : null;
}

export async function saveTweaks(uid: string, key: string, tweaks: VoiceTweaks): Promise<void> {
  await setDoc(doc(db, "users", uid, "voices", key), { tweaks, updatedAt: serverTimestamp() });
}
