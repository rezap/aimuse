// Unit tests for the lyrics formatter (no emulators needed): `npm run test:unit`.
// Fixtures are real Lyria responses from the vocals live test (Backend CI run #9).
import assert from "node:assert/strict";
import { test } from "node:test";

import { formatLyrics, isInstrumental } from "../src/lib/lyrics.ts";

test("clip lyrics: timestamps are removed", () => {
  const raw = "[0.0:5.3] Grey sky on the window pane\n[5.3:10.6] Hear the rhythm of the rain\n[14.8:16.8] (Chasin' the sun!)\n[16.0:] Watching the whole world wake up";
  assert.deepEqual(formatLyrics(raw), [
    {
      heading: null,
      lines: [
        "Grey sky on the window pane",
        "Hear the rhythm of the rain",
        "(Chasin' the sun!)",
        "Watching the whole world wake up",
      ],
    },
  ]);
});

test("lyria 3.5 lyrics: section codes split stanzas and [:] is removed", () => {
  const raw = [
    "[[A0]]",
    "[[B1]]",
    "[:] Rain is tapping on the window pane so slow",
    "[:] City lights are blurring in a amber glow",
    "[[C2]]",
    "[:] Oh let the world just spin on by tonight",
    "[[B3]]",
    "[:] Pages turning slowly as the hours disappear",
  ].join("\n");
  const sections = formatLyrics(raw);
  assert.equal(sections.length, 3);
  assert.deepEqual(sections[0].lines, [
    "Rain is tapping on the window pane so slow",
    "City lights are blurring in a amber glow",
  ]);
  assert.deepEqual(sections[1].lines, ["Oh let the world just spin on by tonight"]);
  assert.ok(sections.every((s) => s.heading === null));
});

test("plain section tags become headings", () => {
  const raw = "[Verse 1]\nWalking through the neon glow\n\n[Chorus]\nWe are the echoes";
  assert.deepEqual(formatLyrics(raw), [
    { heading: "Verse 1", lines: ["Walking through the neon glow"] },
    { heading: "Chorus", lines: ["We are the echoes"] },
  ]);
});

test("instrumental answers have no lyrics", () => {
  for (const raw of ["<instrumental>", "[Instrumental]", "", "  ", null, undefined]) {
    assert.ok(isInstrumental(raw), String(raw));
    assert.deepEqual(formatLyrics(raw), []);
  }
  assert.ok(!isInstrumental("[0.0:3.1] Neon bleeds on window panes"));
});
