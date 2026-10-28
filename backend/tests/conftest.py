import pytest

from aimuse.models import Intent, Section, StyleBible


@pytest.fixture
def style() -> StyleBible:
    return StyleBible(
        id="test-station",
        name="Test Station",
        description="Warm test music.",
        genres=["indie pop"],
        moods=["calm"],
        instruments=["acoustic guitar", "piano"],
        bpm_min=96,
        bpm_max=104,
        keys=["A minor"],
        vocal_style="soft vocal",
        lyric_themes=["testing"],
        structure=[Section(name="Intro", seconds=5), Section(name="Verse", seconds=10)],
        duration_s=10,
        palette=["#000000", "#ffffff"],
        example_intents=[Intent(label="one", theme="a"), Intent(label="two", theme="b")],
    )
