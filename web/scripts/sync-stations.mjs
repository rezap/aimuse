// Copies the public part of the backend's station presets into the web app, so the station
// list in the UI always matches what the Cloud Function can generate.
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const presetDir = join(here, "../../backend/src/aimuse/presets");
const stations = readdirSync(presetDir)
  .filter((f) => f.endsWith(".json"))
  .sort()
  .map((f) => {
    const s = JSON.parse(readFileSync(join(presetDir, f), "utf8"));
    return {
      id: s.id,
      name: s.name,
      description: s.description,
      genres: s.genres,
      moods: s.moods ?? [],
      vocals: (s.vocals ?? "vocals") === "vocals",
      palette: s.palette ?? [],
      ideas: (s.example_intents ?? []).map((i) => i.theme ?? i.label).filter(Boolean),
    };
  });
writeFileSync(join(here, "../src/lib/stations.json"), JSON.stringify(stations, null, 2) + "\n");
console.log(`synced ${stations.length} stations`);
