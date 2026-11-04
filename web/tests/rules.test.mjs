// Security rules tests. Run inside the emulators:
//   firebase emulators:exec --only firestore,storage "npm --prefix web run test:rules"
import { readFileSync } from "node:fs";
import { after, before, beforeEach, test } from "node:test";

import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from "@firebase/rules-unit-testing";
import { addDoc, collection, deleteDoc, doc, getDoc, serverTimestamp, setDoc, updateDoc } from "firebase/firestore";
import { getBytes, ref, uploadString } from "firebase/storage";

let env;

before(async () => {
  env = await initializeTestEnvironment({
    projectId: "demo-aimuse",
    firestore: { rules: readFileSync(new URL("../../firestore.rules", import.meta.url), "utf8") },
    storage: { rules: readFileSync(new URL("../../storage.rules", import.meta.url), "utf8") },
  });
});

after(async () => env?.cleanup());

beforeEach(async () => {
  await env.clearFirestore();
  await env.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();
    await setDoc(doc(db, "users/alice/tracks/t1"), { title: "song", rating: 0, audioPath: "x" });
    await setDoc(doc(db, "users/alice"), { spend: { day: "2026-10-28", usd: 0.08 } });
    await uploadString(ref(ctx.storage(), "users/alice/tracks/t1.mp3"), "audio");
  });
});

const job = (extra = {}) => ({
  stationId: "late-night-lofi",
  mood: "calm",
  theme: "rain",
  energy: 0.4,
  vocals: null,
  status: "queued",
  createdAt: serverTimestamp(),
  ...extra,
});

test("owner can queue a valid job", async () => {
  const db = env.authenticatedContext("alice").firestore();
  await assertSucceeds(addDoc(collection(db, "users/alice/jobs"), job()));
});

test("job requests are validated", async () => {
  const db = env.authenticatedContext("alice").firestore();
  const jobs = collection(db, "users/alice/jobs");
  await assertFails(addDoc(jobs, job({ status: "done" })));
  await assertFails(addDoc(jobs, job({ energy: 2 })));
  await assertFails(addDoc(jobs, job({ theme: "x".repeat(201) })));
  await assertFails(addDoc(jobs, job({ trackId: "sneaky" })));
  await assertFails(addDoc(jobs, job({ createdAt: new Date(0) })));
  await assertSucceeds(addDoc(jobs, job({ inspiration: "Bob Dylan" })));
  await assertFails(addDoc(jobs, job({ inspiration: "x".repeat(81) })));
  await assertFails(addDoc(jobs, job({ inspiration: 42 })));
  await assertSucceeds(addDoc(jobs, job({ lyrics: "line one\nline two" })));
  await assertSucceeds(addDoc(jobs, job({ singer: "female" })));
  await assertFails(addDoc(jobs, job({ singer: "robot" })));
  await assertSucceeds(addDoc(jobs, job({ voiceTweaks: { pitch: -1, grit: 1, spoken: 0, space: 0 } })));
  await assertFails(addDoc(jobs, job({ voiceTweaks: { grit: 2 } })));
  await assertFails(addDoc(jobs, job({ voiceTweaks: { volume: 1 } })));
  await assertFails(addDoc(jobs, job({ lyrics: "x".repeat(3001) })));
});

test("nobody can queue jobs for someone else or edit jobs", async () => {
  const bob = env.authenticatedContext("bob").firestore();
  await assertFails(addDoc(collection(bob, "users/alice/jobs"), job()));
  const anon = env.unauthenticatedContext().firestore();
  await assertFails(addDoc(collection(anon, "users/alice/jobs"), job()));

  const alice = env.authenticatedContext("alice").firestore();
  const r = await addDoc(collection(alice, "users/alice/jobs"), job());
  await assertFails(updateDoc(r, { status: "done" }));
});

test("owner can clear finished, failed or stuck jobs, not running ones", async () => {
  const minutesAgo = (m) => new Date(Date.now() - m * 60_000);
  await env.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();
    await setDoc(doc(db, "users/alice/jobs/failed"), job({ status: "failed", createdAt: new Date() }));
    await setDoc(doc(db, "users/alice/jobs/done"), job({ status: "done", createdAt: new Date() }));
    await setDoc(doc(db, "users/alice/jobs/running"), job({ status: "running", createdAt: minutesAgo(1) }));
    await setDoc(doc(db, "users/alice/jobs/stuck"), job({ status: "running", createdAt: minutesAgo(20) }));
  });
  const bob = env.authenticatedContext("bob").firestore();
  await assertFails(deleteDoc(doc(bob, "users/alice/jobs/failed")));
  const alice = env.authenticatedContext("alice").firestore();
  await assertSucceeds(deleteDoc(doc(alice, "users/alice/jobs/failed")));
  await assertSucceeds(deleteDoc(doc(alice, "users/alice/jobs/done")));
  await assertFails(deleteDoc(doc(alice, "users/alice/jobs/running")));
  await assertSucceeds(deleteDoc(doc(alice, "users/alice/jobs/stuck")));
});

test("tracks: owner reads, rates and deletes; nothing else", async () => {
  const alice = env.authenticatedContext("alice").firestore();
  const t = doc(alice, "users/alice/tracks/t1");
  await assertSucceeds(getDoc(t));
  await assertSucceeds(updateDoc(t, { rating: 1 }));
  await assertFails(updateDoc(t, { rating: 5 }));
  await assertFails(updateDoc(t, { title: "renamed" }));
  await assertFails(setDoc(doc(alice, "users/alice/tracks/new"), { title: "fake" }));
  await assertFails(setDoc(doc(alice, "users/alice"), { spend: { usd: 0 } }));

  const bob = env.authenticatedContext("bob").firestore();
  await assertFails(getDoc(doc(bob, "users/alice/tracks/t1")));
  await assertFails(getDoc(doc(bob, "users/alice")));

  await assertSucceeds(deleteDoc(t));
});

test("saved voices: owner only, valid nudges only", async () => {
  const alice = env.authenticatedContext("alice").firestore();
  const v = doc(alice, "users/alice/voices/bob-dylan");
  await assertSucceeds(setDoc(v, { tweaks: { grit: 1, space: -1 }, updatedAt: serverTimestamp() }));
  await assertSucceeds(getDoc(v));
  await assertFails(setDoc(v, { tweaks: { grit: 3 }, updatedAt: serverTimestamp() }));
  await assertFails(setDoc(v, { tweaks: {}, updatedAt: serverTimestamp(), extra: 1 }));
  const bob = env.authenticatedContext("bob").firestore();
  await assertFails(getDoc(doc(bob, "users/alice/voices/bob-dylan")));
  await assertFails(setDoc(doc(bob, "users/alice/voices/x"), { tweaks: {}, updatedAt: serverTimestamp() }));
});

test("the artist-style cache is server-only", async () => {
  const alice = env.authenticatedContext("alice").firestore();
  await assertFails(getDoc(doc(alice, "influences/bob-dylan")));
  await assertFails(setDoc(doc(alice, "influences/bob-dylan"), { traits: {} }));
});

test("audio files: only the owner can read; nobody can upload", async () => {
  const path = "users/alice/tracks/t1.mp3";
  await assertSucceeds(getBytes(ref(env.authenticatedContext("alice").storage(), path)));
  await assertFails(getBytes(ref(env.authenticatedContext("bob").storage(), path)));
  await assertFails(uploadString(ref(env.authenticatedContext("alice").storage(), "users/alice/tracks/x.mp3"), "a"));
});
