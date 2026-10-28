import os

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


def pytest_collection_modifyitems(config, items):
    """Live tests call the paid Lyria API: run them only when AIMUSE_LIVE=1 and a key is set."""
    if os.environ.get("AIMUSE_LIVE") == "1" and os.environ.get("GEMINI_API_KEY"):
        return
    skip = pytest.mark.skip(reason="live API test: set AIMUSE_LIVE=1 and GEMINI_API_KEY to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
