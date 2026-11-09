import os
from pathlib import Path

from PIL import Image

from media.derivatives import DerivativeCache


def make_jxl(path: Path, size: tuple[int, int] = (64, 48)) -> Path:
    Image.new("RGB", size, (10, 20, 30)).save(path, format="JXL", lossless=True)
    return path


def test_thumb_is_avif_and_cached(tmp_path):
    source = make_jxl(tmp_path / "a.jxl")
    cache = DerivativeCache(tmp_path / "cache", max_bytes=10_000_000)
    output = cache.thumb(source, "Film/a.jxl")
    assert output.suffix == ".avif"
    with Image.open(output) as image:
        assert image.format == "AVIF"
        assert image.width == 64
    assert cache.thumb(source, "Film/a.jxl") == output


def test_cache_key_changes_with_source_mtime(tmp_path):
    source = make_jxl(tmp_path / "a.jxl")
    cache = DerivativeCache(tmp_path / "cache", max_bytes=10_000_000)
    first = cache.thumb(source, "Film/a.jxl")
    os.utime(source, ns=(0, source.stat().st_mtime_ns + 1_000_000))
    assert cache.thumb(source, "Film/a.jxl") != first


def test_huge_image_stays_within_pixel_budget(tmp_path):
    source = make_jxl(tmp_path / "big.jxl", (2000, 1000))
    cache = DerivativeCache(tmp_path / "cache", max_bytes=10_000_000, pixel_budget=10_000)
    output = cache.thumb(source, "Film/big.jxl")
    with Image.open(output) as image:
        assert image.width * image.height <= 10_000


def test_lens_uses_long_edge(tmp_path):
    source = make_jxl(tmp_path / "wide.jxl", (2000, 1000))
    cache = DerivativeCache(tmp_path / "cache", max_bytes=10_000_000, lens_long_edge=100)
    output = cache.lens(source, "Film/wide.jxl")
    with Image.open(output) as image:
        assert max(image.size) == 100
