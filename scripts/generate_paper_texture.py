"""Generate the static paper-grain tile used by the SKEER surface treatment.

A pre-rasterized image is intentional: a full-screen SVG feTurbulence filter with
mix-blend-mode is expensive for the browser compositor and can make Chromium's
GPU process unstable during continuous pointer interaction.
"""
from __future__ import annotations

import random
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web" / "public" / "brand" / "paper-grain.png"


def main() -> None:
    rng = random.Random(118)
    size = 160
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            # Mostly transparent warm-dark pinpricks with a light fibre here and
            # there. The strength is controlled by CSS opacity, not by blending.
            value = rng.random()
            if value < 0.055:
                pixels[x, y] = (41, 40, 33, rng.randint(12, 52))
            elif value < 0.09:
                pixels[x, y] = (255, 252, 244, rng.randint(10, 38))
            elif value < 0.18:
                pixels[x, y] = (41, 40, 33, rng.randint(4, 16))
    image.save(OUTPUT, optimize=True)
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
