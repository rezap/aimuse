/**
 * Turns the raw lyrics text Lyria returns into readable verses.
 *
 * Lyria marks up its lyrics with timing and section codes, e.g.
 *   Clip:  "[0.0:5.3] Grey sky on the window pane"
 *   3.5:   "[[A0]]" / "[[B1]]" section markers and "[:] Rain is tapping…" lines
 * and answers "<instrumental>" when it made no vocals. Plain "[Verse 1]"-style tags (from
 * user-written lyrics) are kept as section headings.
 */

export type LyricSection = { heading: string | null; lines: string[] };

const TIMESTAMP = /^\[\s*\d*(?:\.\d+)?\s*:\s*\d*(?:\.\d+)?\s*\]\s*/; // [0.0:5.3]  [14.8:]  [:]
const SECTION_CODE = /^\[\[\s*[A-Za-z]\d*\s*\]\]$/; // [[A0]]
const HEADING = /^\[([^\]]+)\]$/; // [Verse 1]

export function isInstrumental(raw: string | null | undefined): boolean {
  const t = (raw ?? "").trim().replace(/^[<[(\s]+|[>\])\s]+$/g, "").toLowerCase();
  return t === "" || t === "instrumental" || t === "instrumental only";
}

export function formatLyrics(raw: string | null | undefined): LyricSection[] {
  if (isInstrumental(raw)) return [];
  const sections: LyricSection[] = [];
  let current: LyricSection = { heading: null, lines: [] };
  const flush = () => {
    if (current.lines.length || current.heading) sections.push(current);
  };

  for (const rawLine of (raw ?? "").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      // A blank line ends a stanza.
      if (current.lines.length) {
        flush();
        current = { heading: null, lines: [] };
      }
      continue;
    }
    if (SECTION_CODE.test(line)) {
      flush();
      current = { heading: null, lines: [] };
      continue;
    }
    const heading = line.match(HEADING);
    if (heading && !TIMESTAMP.test(line)) {
      flush();
      current = { heading: heading[1].trim(), lines: [] };
      continue;
    }
    const text = line.replace(TIMESTAMP, "").trim();
    if (text) current.lines.push(text);
  }
  flush();
  return sections.filter((s) => s.lines.length > 0);
}
