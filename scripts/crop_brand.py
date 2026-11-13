"""Crop the approved SKEER logo artwork into header/favicon derivatives.

The supplied asset is an ivory-background PNG. Cropping removes only the empty
margin; the mark itself is not recoloured or reconstructed.
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "web" / "public" / "brand"
SOURCE = BRAND / "skeer-logo-ivory.png"


def content_box(image: Image.Image, tolerance: int = 28) -> tuple[int, int, int, int]:
    pixels = image.convert("RGB").load()
    width, height = image.size
    background = pixels[0, 0]
    min_x, min_y, max_x, max_y = width, height, 0, 0
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            if abs(r - background[0]) + abs(g - background[1]) + abs(b - background[2]) > tolerance:
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    return min_x, min_y, max_x + 1, max_y + 1


def main() -> None:
    image = Image.open(SOURCE).convert("RGB")
    box = content_box(image)
    padding = 24
    left = max(0, box[0] - padding)
    top = max(0, box[1] - padding)
    right = min(image.width, box[2] + padding)
    bottom = min(image.height, box[3] + padding)
    wordmark = image.crop((left, top, right, bottom))
    wordmark.save(BRAND / "skeer-wordmark.png", optimize=True)

    # The first orange block is the mark; crop it for the compact favicon and
    # empty-state stamps. It remains the approved artwork.
    orange = []
    rgb = image.load()
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            r, g, b = rgb[x, y]
            if r > 180 and g < 160 and b < 90:
                orange.append((x, y))
    if orange:
        ox0 = min(x for x, _ in orange)
        oy0 = min(y for _, y in orange)
        ox1 = max(x for x, _ in orange)
        oy1 = max(y for _, y in orange)
        pad = 18
        mark = image.crop((max(0, ox0 - pad), max(0, oy0 - pad),
                           min(image.width, ox1 + pad), min(image.height, oy1 + pad)))
        mark.save(BRAND / "skeer-mark.png", optimize=True)
        mark.resize((128, 128), Image.LANCZOS).save(BRAND / "skeer-favicon.png", optimize=True)

    print(f"wordmark: {wordmark.size}")
    print("wrote skeer-wordmark.png, skeer-mark.png, skeer-favicon.png")


if __name__ == "__main__":
    main()
