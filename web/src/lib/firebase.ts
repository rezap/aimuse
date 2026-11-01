import { getApps, initializeApp } from "firebase/app";
import { connectAuthEmulator, getAuth } from "firebase/auth";
import { connectFirestoreEmulator, getFirestore } from "firebase/firestore";
import { connectFunctionsEmulator, getFunctions } from "firebase/functions";
import { connectStorageEmulator, getStorage } from "firebase/storage";

const useEmulators = process.env.NEXT_PUBLIC_USE_EMULATORS === "1";
export const usingEmulators = useEmulators;

const config = useEmulators
  ? {
      apiKey: "demo-key",
      authDomain: "demo-aimuse.firebaseapp.com",
      projectId: "demo-aimuse",
      storageBucket: "demo-aimuse.appspot.com",
      appId: "demo-app",
    }
  : {
      apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
      authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
      projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
      storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
      appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
    };

export const firebaseConfigured = Boolean(config.apiKey && config.projectId);

// Without settings the SDK would throw at import and break the build; use placeholders so the
// page still renders and shows the "not configured" notice instead.
if (!firebaseConfigured) {
  Object.assign(config, { apiKey: "not-configured", projectId: "not-configured" });
}

const app = getApps()[0] ?? initializeApp(config);
export const auth = getAuth(app);
export const db = getFirestore(app);
export const storage = getStorage(app);
export const functions = getFunctions(app);

let connected = false;
if (useEmulators && typeof window !== "undefined" && !connected) {
  connected = true;
  connectAuthEmulator(auth, "http://127.0.0.1:9099", { disableWarnings: true });
  connectFirestoreEmulator(db, "127.0.0.1", 8080);
  connectStorageEmulator(storage, "127.0.0.1", 9199);
  connectFunctionsEmulator(functions, "127.0.0.1", 5001);
}
