"""Anchor image: a deterministic mood-board image derived from a style bible's palette.

Lyria accepts images as conditioning input, so attaching the same image to every track of a
station is a cheap extra consistency signal.
"""

from __future__ import annotations

import hashlib
import io

import numpy as np
from PIL import Image

from .models import StyleBible

_DEFAULT_PALETTE = ["#1d2b53", "#7e2553", "#ff77a8", "#ffccaa"]
_SIZE = 512


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) != 6:
        raise ValueError(f"palette colours must be #rrggbb, got {color!r}")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def anchor_image_png(style: StyleBible) -> bytes:
    palette = [_hex_to_rgb(c) for c in (style.palette or _DEFAULT_PALETTE)]
    if len(palette) == 1:
        palette = palette * 2
    seed = int.from_bytes(hashlib.sha256(f"{style.id}:{style.version}".encode()).digest()[:4])
    rng = np.random.default_rng(seed)

    # Vertical gradient through the palette, plus soft seeded noise for texture.
    stops = np.linspace(0, 1, len(palette))
    t = np.linspace(0, 1, _SIZE)
    cols = np.array(palette, dtype=float)
    gradient = np.stack([np.interp(t, stops, cols[:, ch]) for ch in range(3)], axis=-1)
    img = np.repeat(gradient[:, None, :], _SIZE, axis=1)
    img += rng.normal(0, 6, size=img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG", optimize=True)
    return buf.getvalue()
