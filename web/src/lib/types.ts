import type { Timestamp } from "firebase/firestore";

export type Station = {
  id: string;
  name: string;
  description: string;
  genres: string[];
  moods: string[];
  vocals: boolean;
  palette: string[];
  ideas: string[];
};

export type JobStatus = "queued" | "running" | "done" | "failed";

export type Job = {
  id: string;
  stationId: string;
  mood: string | null;
  theme: string | null;
  energy: number | null;
  vocals: boolean | null;
  lyrics?: string | null;
  status: JobStatus;
  error?: string;
  createdAt?: Timestamp;
};

export type Track = {
  id: string;
  title: string;
  stationId: string;
  stationName: string;
  mood: string | null;
  theme: string | null;
  vocals: boolean;
  singer?: "male" | "female" | "duet" | null;
  vocalsDelivered?: boolean | null;
  inspiration?: string | null;
  influences?: string | null;
  inspirationNote?: string | null;
  ownLyrics?: boolean;
  audioPath: string;
  mimeType: string;
  durationS: number | null;
  bpm: number | null;
  key: string | null;
  lyrics: string | null;
  prompt: string;
  model: string;
  rating: -1 | 0 | 1;
  createdAt?: Timestamp;
};
