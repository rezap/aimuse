"use client";

import { collection, deleteDoc, doc, limit, onSnapshot, orderBy, query } from "firebase/firestore";
import { useEffect, useState } from "react";

import { db } from "@/lib/firebase";
import { stations } from "@/lib/music";
import type { Job } from "@/lib/types";

const LABEL: Record<Job["status"], string> = {
  queued: "Waiting…",
  running: "Composing… (about a minute)",
  done: "Ready",
  failed: "Failed",
};

// The function gives up after 9 minutes; a job still unfinished after 15 is stuck.
const STUCK_MS = 15 * 60_000;

/** Failed and stuck jobs can be cleared (the security rules allow exactly these). */
function canClear(j: Job): boolean {
  if (j.status === "failed" || j.status === "done") return true;
  const created = j.createdAt?.toMillis();
  return created !== undefined && Date.now() - created > STUCK_MS;
}

/** A short title: the topic or the first line of the lyrics, never the whole text. */
function jobTitle(j: Job): string {
  const text = (j.theme || j.lyrics || j.mood || "New song").trim();
  const first = text.split("\n")[0].trim();
  return first.length > 60 ? `${first.slice(0, 57)}…` : first;
}

/** Songs being made right now, plus recent failures. Finished songs show up in the library. */
export function JobList({ uid }: { uid: string }) {
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => {
    const q = query(collection(db, "users", uid, "jobs"), orderBy("createdAt", "desc"), limit(8));
    return onSnapshot(q, (snap) =>
      setJobs(snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<Job, "id">) }))),
    );
  }, [uid]);

  const visible = jobs.filter((j) => j.status !== "done");
  if (visible.length === 0) return null;

  const clear = (j: Job) => deleteDoc(doc(db, "users", uid, "jobs", j.id)).catch(() => undefined);
  const clearable = visible.filter(canClear);

  return (
    <section className="card">
      <div className="row">
        <h2 className="grow">In progress</h2>
        {clearable.length > 1 && (
          <button className="ghost small" onClick={() => clearable.forEach(clear)}>
            Clear all
          </button>
        )}
      </div>
      <ul className="jobs">
        {visible.map((j) => (
          <li key={j.id} className={`job ${j.status}`}>
            <span className="dot" aria-hidden />
            <span className="grow">
              <strong>{jobTitle(j)}</strong>
              <span className="muted"> · {stations.find((s) => s.id === j.stationId)?.name}</span>
            </span>
            <span>{LABEL[j.status]}</span>
            {canClear(j) && (
              <button className="ghost small" aria-label="Clear" title="Clear" onClick={() => clear(j)}>
                ✕
              </button>
            )}
            {j.error && <p className="error full">{j.error}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}
