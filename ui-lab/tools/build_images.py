"""Build sample imagery for the UI lab from the imported JXL archive.

Run from the repo root:

    uv run --group dev python ui-lab/tools/build_images.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pillow_jxl  # noqa: F401  (registers the JXL opener)
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "test-wallpapers" / "Your Name. [2016][tmdb-372058]"
OUT = ROOT / "ui-lab" / "assets" / "images"

FRAME_RE = re.compile(r" - (?P<index>\d{4})\+\.jxl$")


def save(image: Image.Image, path: Path, *, width: int, quality: int = 72) -> None:
    if image.width > width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    image = image.convert("RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "WEBP", quality=quality, method=6)
    print(  # noqa: T201  (CLI progress output)
        f"{path.relative_to(ROOT)}  {image.width}x{image.height}  {path.stat().st_size // 1024} KiB"
    )


def main() -> None:
    frames = sorted(
        (int(match.group("index")), path) for path in SOURCE.glob("*.jxl") if (match := FRAME_RE.search(path.name))
    )
    if not frames:
        raise SystemExit(f"no frames found in {SOURCE}")

    for index, path in frames[:16]:
        with Image.open(path) as image:
            save(image, OUT / f"frame-{index:02d}.webp", width=1000, quality=72)

    for index, path in frames[:4]:
        with Image.open(path) as image:
            save(image, OUT / f"lens-{index:02d}.webp", width=1600, quality=70)

    with Image.open(frames[0][1]) as image:
        save(image, OUT / "hero.webp", width=1800, quality=68)

    cover = SOURCE / ".cover.jxl"
    if cover.exists():
        with Image.open(cover) as image:
            save(image, OUT / "poster.webp", width=640, quality=78)


if __name__ == "__main__":
    main()
