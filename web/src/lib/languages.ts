/** Languages a song can be sung in. Keep in step with backend/src/aimuse/languages.py. */
export type LanguageCode = "en" | "es" | "fr" | "de" | "pt" | "hi" | "ja" | "ko" | "fa";

export type Language = {
  code: LanguageCode;
  name: string;
  latin: boolean; // written in Latin letters, so "sung from Latin letters" makes no sense
  official: boolean; // in Google's documented list of languages Lyria sings
};

export const LANGUAGES: Language[] = [
  { code: "en", name: "English", latin: true, official: true },
  { code: "es", name: "Spanish", latin: true, official: true },
  { code: "fa", name: "Persian (Farsi)", latin: false, official: false },
  { code: "fr", name: "French", latin: true, official: true },
  { code: "de", name: "German", latin: true, official: true },
  { code: "pt", name: "Portuguese", latin: true, official: true },
  { code: "hi", name: "Hindi", latin: false, official: true },
  { code: "ja", name: "Japanese", latin: false, official: true },
  { code: "ko", name: "Korean", latin: false, official: true },
];

/** Who writes the words, and in which letters Lyria gets them. */
export type LyricsMode = "lyria" | "written" | "romanized";

export const languageByCode = (code: string | null | undefined) =>
  LANGUAGES.find((l) => l.code === code);

export function lyricsModeLabel(
  mode: LyricsMode | null | undefined,
  ownLyrics: boolean,
  fromStory = false,
): string {
  if (fromStory) {
    return mode === "romanized"
      ? "lyrics by Gemini from your story, sung from Latin letters"
      : "lyrics by Gemini from your story";
  }
  if (mode === "romanized") return ownLyrics ? "sung from Latin letters" : "lyrics by Gemini, sung from Latin letters";
  if (mode === "written") return ownLyrics ? "sung as written" : "lyrics by Gemini";
  return ownLyrics ? "sung as written" : "lyrics by Lyria";
}
