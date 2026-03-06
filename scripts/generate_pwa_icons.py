"""
Generate white-on-blue PWA icons for Android home screen.

The original logo is a blue microphone on white background.
This script converts it to a white logo on the blue theme background
so the icon is readable on any Android home screen.
"""
import sys
from pathlib import Path
from PIL import Image

REPO_ROOT = Path(__file__).parent.parent
LOGOS_DIR = REPO_ROOT / "frontend" / "public" / "images" / "logos"
SOURCE = LOGOS_DIR / "original-logo.png"
OUTPUT_192 = LOGOS_DIR / "web-app-manifest-192x192.png"
OUTPUT_512 = LOGOS_DIR / "web-app-manifest-512x512.png"

# Blue theme background color
BG_COLOR = (14, 22, 40)      # #0e1628 — deep navy blue

# Threshold: pixels brighter than this (in grayscale) are treated as background
WHITE_THRESHOLD = 200


def make_white_on_blue(source_path: Path, size: int) -> Image.Image:
    """
    1. Load source PNG
    2. Convert background (near-white) pixels to transparent
    3. Convert remaining (logo) pixels to white
    4. Composite onto solid blue background
    """
    src = Image.open(source_path).convert("RGBA")

    # Resize logo to fit within the safe zone (80% for maskable)
    safe = int(size * 0.75)
    src_resized = src.resize((safe, safe), Image.LANCZOS)

    # Create output canvas with blue background
    canvas = Image.new("RGBA", (size, size), (*BG_COLOR, 255))

    # For each pixel in the resized logo:
    # - near-white → transparent (background)
    # - everything else → white (logo outline)
    pixels = src_resized.load()
    w, h = src_resized.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            # Treat near-white or fully transparent as background
            brightness = (r + g + b) / 3
            if a < 30 or brightness > WHITE_THRESHOLD:
                pixels[x, y] = (0, 0, 0, 0)  # transparent
            else:
                # Make the logo pixel white, preserving alpha
                pixels[x, y] = (255, 255, 255, a)

    # Centre the logo on the canvas
    offset = (size - safe) // 2
    canvas.paste(src_resized, (offset, offset), src_resized)

    return canvas.convert("RGB")


def main() -> None:
    if not SOURCE.exists():
        print(f"ERROR: source not found: {SOURCE}", file=sys.stderr)
        sys.exit(1)

    for size, out in [(192, OUTPUT_192), (512, OUTPUT_512)]:
        img = make_white_on_blue(SOURCE, size)
        img.save(out, "PNG", optimize=True)
        print(f"Written {size}x{size} → {out}")

    print("Done.")


if __name__ == "__main__":
    main()
