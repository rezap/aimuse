"""Built-in style bibles (stations). Users can also pass a path to their own JSON file."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from .models import StyleBible


def list_presets() -> list[str]:
    files = resources.files("aimuse").joinpath("presets").iterdir()
    return sorted(f.name.removesuffix(".json") for f in files if f.name.endswith(".json"))


def load_style(name_or_path: str) -> StyleBible:
    path = Path(name_or_path)
    if path.suffix == ".json" and path.exists():
        text = path.read_text()
    else:
        res = resources.files("aimuse").joinpath("presets", f"{name_or_path}.json")
        if not res.is_file():
            raise FileNotFoundError(
                f"no preset {name_or_path!r}; available: {', '.join(list_presets())}"
            )
        text = res.read_text()
    return StyleBible.model_validate(json.loads(text))
