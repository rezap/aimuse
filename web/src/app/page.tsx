"use client";

import {
  GoogleAuthProvider,
  onAuthStateChanged,
  signInAnonymously,
  signInWithPopup,
  signOut,
  type User,
} from "firebase/auth";
import { useEffect, useState } from "react";

import { Composer } from "@/components/Composer";
import { JobList } from "@/components/JobList";
import { Library } from "@/components/Library";
import { auth, firebaseConfigured, usingEmulators } from "@/lib/firebase";

export default function Home() {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => onAuthStateChanged(auth, setUser), []);

  async function signIn(test = false) {
    setError(null);
    try {
      if (test) await signInAnonymously(auth);
      else await signInWithPopup(auth, new GoogleAuthProvider());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <main>
      <header className="top">
        <h1>
          AI <span>Muse</span>
        </h1>
        {user && (
          <div className="me">
            <span className="muted">{user.displayName ?? user.email ?? "Test user"}</span>
            <button className="ghost" onClick={() => signOut(auth)}>
              Sign out
            </button>
          </div>
        )}
      </header>

      {!firebaseConfigured && (
        <p className="error">
          Firebase isn't configured. Copy web/.env.example to web/.env.local and fill it in, or set
          NEXT_PUBLIC_USE_EMULATORS=1.
        </p>
      )}

      {user === undefined && <p className="muted">Loading…</p>}

      {user === null && (
        <section className="hero">
          <p>Music made for your taste. Pick a vibe, get a song you can keep.</p>
          <div className="actions center">
            <button className="primary" onClick={() => signIn()}>
              Sign in with Google
            </button>
            {usingEmulators && <button onClick={() => signIn(true)}>Test user (emulator)</button>}
          </div>
          {error && <p className="error">{error}</p>}
        </section>
      )}

      {user && (
        <>
          <Composer uid={user.uid} />
          <JobList uid={user.uid} />
          <Library uid={user.uid} />
        </>
      )}
    </main>
  );
}
