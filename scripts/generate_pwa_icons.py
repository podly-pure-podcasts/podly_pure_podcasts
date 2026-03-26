"""
Generate blue-backed PWA icons from the current Podly logo.

Android adaptive icons look best when the mark sits inside a clear safe zone
with a solid background. This keeps the Podly logo readable on busy home
screens without depending on transparency.
"""
import sys
from pathlib import Path
from PIL import Image

REPO_ROOT = Path(__file__).parent.parent
LOGOS_DIR = REPO_ROOT / "frontend" / "public" / "images" / "logos"
SOURCE = LOGOS_DIR / "original-logo.png"
OUTPUT_192 = LOGOS_DIR / "web-app-manifest-192x192.png"
OUTPUT_512 = LOGOS_DIR / "web-app-manifest-512x512.png"
MASKABLE_192 = LOGOS_DIR / "manifest-icon-192.maskable.png"
MASKABLE_512 = LOGOS_DIR / "manifest-icon-512.maskable.png"

BG_COLOR = (37, 95, 156)


def make_icon(source_path: Path, size: int, safe_zone_ratio: float) -> Image.Image:
    """Place the current logo on a solid square canvas."""
    src = Image.open(source_path).convert("RGBA")
    safe = int(size * safe_zone_ratio)
    src_resized = src.resize((safe, safe), Image.LANCZOS)

    canvas = Image.new("RGBA", (size, size), (*BG_COLOR, 255))
    offset = (size - safe) // 2
    canvas.paste(src_resized, (offset, offset), src_resized)

    return canvas.convert("RGB")


def main() -> None:
    if not SOURCE.exists():
        print(f"ERROR: source not found: {SOURCE}", file=sys.stderr)
        sys.exit(1)

    outputs = [
        (192, OUTPUT_192, 1.0),
        (512, OUTPUT_512, 1.0),
        (192, MASKABLE_192, 0.75),
        (512, MASKABLE_512, 0.75),
    ]

    for size, out, safe_zone_ratio in outputs:
        img = make_icon(SOURCE, size, safe_zone_ratio=safe_zone_ratio)
        img.save(out, "PNG", optimize=True)
        print(f"Written {size}x{size} → {out}")

    print("Done.")


if __name__ == "__main__":
    main()
