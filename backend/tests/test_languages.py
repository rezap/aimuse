import json

import httpx
import pytest

from aimuse.languages import LANGUAGES, LyricsMode, get_language, script_of
from aimuse.lyrics_writer import (
    FakeLyricsWriter,
    GeminiLyricsWriter,
    LyricsError,
    prepare_lyrics,
)
from aimuse.models import Intent, Vocals
from aimuse.presets import load_style
from aimuse.prompt import compile_prompt

STYLE = load_style("rainy-morning-indie")


def _reply(payload):
    return {
        "steps": [
            {"type": "model_output", "content": [{"type": "text", "text": json.dumps(payload)}]}
        ]
    }


def test_language_list_and_validation():
    assert LANGUAGES["es"].official and not LANGUAGES["fa"].official
    assert not LANGUAGES["fa"].latin and LANGUAGES["es"].latin
    assert get_language(None) is None
    with pytest.raises(ValueError):
        Intent(language="xx")


def test_script_detection():
    assert script_of("[Verse 1]\nباران آرام می‌بارد") == "Persian/Arabic"
    assert script_of("[0.0:4.0] baaraan aaraam mibaarad") == "Latin"
    assert script_of("باران rain falls slowly and softly") == "mixed"
    assert script_of("<instrumental>") == "Latin" and script_of("") == "none"


def test_prompt_names_the_language_lyria_writes_in():
    p = compile_prompt(STYLE, Intent(language="es", vocals=Vocals.VOCALS)).text
    assert "sung lyrics in Spanish, not an instrumental" in p
    assert "The lyrics are original, in Spanish" in p
    # Without a language, the station's language is used as before.
    assert "The lyrics are original, in English" in compile_prompt(STYLE, Intent()).text


def test_duet_in_two_languages():
    intent = Intent(language="es", duet_language="en", vocals=Vocals.VOCALS)
    p = compile_prompt(STYLE, intent).text
    assert "vocal duet" in p and "sings in Spanish and a second singer answers in English" in p
    assert "The lyrics are original, in Spanish and English" in p
    same = compile_prompt(STYLE, Intent(language="en", duet_language="en")).text
    assert "duet" not in same


def test_lyria_mode_changes_nothing():
    intent = Intent(language="fa")
    prepared = prepare_lyrics(STYLE, intent, LyricsMode.LYRIA, FakeLyricsWriter())
    assert prepared.intent is intent and prepared.display is None


def test_written_mode_sends_native_script_lyrics():
    writer = FakeLyricsWriter()
    prepared = prepare_lyrics(STYLE, Intent(language="fa"), LyricsMode.WRITTEN, writer)
    assert writer.calls == ["write:fa"]
    assert script_of(prepared.intent.lyrics) == "Persian/Arabic"
    assert prepared.display == prepared.intent.lyrics
    p = compile_prompt(STYLE, prepared.intent).text
    assert "Sing the lyrics below in Persian (Farsi) exactly as written" in p
    assert "Lyrics:\n[Verse 1]\nباران" in p


def test_romanized_mode_sends_latin_letters_and_keeps_the_script_for_display():
    prepared = prepare_lyrics(
        STYLE, Intent(language="fa"), LyricsMode.ROMANIZED, FakeLyricsWriter()
    )
    assert prepared.intent.lyrics_romanized
    assert script_of(prepared.intent.lyrics) == "Latin"
    assert script_of(prepared.display) == "Persian/Arabic"
    p = compile_prompt(STYLE, prepared.intent).text
    assert "Persian (Farsi) written in Latin letters" in p and "baaraan" in p


def test_own_lyrics_romanized_or_sung_as_written():
    own = "[Verse 1]\nباران آرام می‌بارد\nروی شیشه‌ی پنجره\n\n[Chorus]\nبمان با من امشب"
    writer = FakeLyricsWriter()
    roman = prepare_lyrics(STYLE, Intent(language="fa", lyrics=own), LyricsMode.ROMANIZED, writer)
    assert writer.calls == ["romanize:fa"] and roman.display == own
    assert roman.intent.lyrics.startswith("[Verse 1]\nbaaraan")
    as_is = prepare_lyrics(STYLE, Intent(language="fa", lyrics=own), LyricsMode.WRITTEN, writer)
    assert as_is.intent.lyrics == own and writer.calls == ["romanize:fa"]


def test_romanizing_a_latin_language_just_writes_it():
    writer = FakeLyricsWriter()
    prepared = prepare_lyrics(STYLE, Intent(language="es"), LyricsMode.ROMANIZED, writer)
    assert writer.calls == ["write:es"] and not prepared.intent.lyrics_romanized
    assert prepared.mode == LyricsMode.WRITTEN


def test_gemini_writer_request_and_fallback_romanization():
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        if "Transliterate" in body["system_instruction"]:
            return httpx.Response(200, json=_reply({"romanized": "salaam"}))
        return httpx.Response(200, json=_reply({"lyrics": "[Verse 1]\nسلام"}))

    writer = GeminiLyricsWriter("k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    out = writer.write(LANGUAGES["fa"], "a song about rain", romanize=True)
    assert out.text == "[Verse 1]\nسلام" and out.romanized == "salaam"
    assert bodies[0]["input"].startswith("Language: Persian (Farsi).")
    assert "never quote or adapt existing songs" in bodies[0]["system_instruction"]
    assert len(bodies) == 2  # no romanization in the answer -> asked separately


def test_gemini_writer_errors():
    bad = GeminiLyricsWriter(
        "k", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    )
    with pytest.raises(LyricsError):
        bad.write(LANGUAGES["fa"], "x")
    empty = GeminiLyricsWriter(
        "k",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=_reply({"lyrics": ""}))
            )
        ),
    )
    with pytest.raises(LyricsError):
        empty.write(LANGUAGES["es"], "x")
    with pytest.raises(LyricsError):
        prepare_lyrics(STYLE, Intent(language="fa"), LyricsMode.WRITTEN, None)


def test_firestore_rules_list_the_same_languages():
    from pathlib import Path

    rules = (Path(__file__).parents[2] / "firestore.rules").read_text()
    listed = rules.split("function validLanguage")[1].split("]")[0]
    assert sorted(c.strip(" '[\n") for c in listed.split("in [")[1].split(",")) == sorted(LANGUAGES)
