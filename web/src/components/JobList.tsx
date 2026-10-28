"use client";

import { collection, limit, onSnapshot, orderBy, query } from "firebase/firestore";
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

  return (
    <section className="card">
      <h2>In progress</h2>
      <ul className="jobs">
        {visible.map((j) => (
          <li key={j.id} className={`job ${j.status}`}>
            <span className="dot" aria-hidden />
            <span className="grow">
              <strong>{j.theme || j.mood || "New song"}</strong>
              <span className="muted"> · {stations.find((s) => s.id === j.stationId)?.name}</span>
            </span>
            <span>{LABEL[j.status]}</span>
            {j.error && <p className="error full">{j.error}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}
