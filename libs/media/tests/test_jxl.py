from pathlib import Path

from PIL import Image

from media.jxl import encode_jxl, probe_dimensions


def make_png(path: Path, size: tuple[int, int] = (32, 24), color: tuple[int, int, int] = (10, 20, 30)) -> Path:
    image = Image.new("RGB", size, color)
    image.putpixel((1, 1), (200, 100, 50))
    image.save(path)
    return path


def test_encode_jxl_round_trip_pixels(tmp_path):
    source = make_png(tmp_path / "a.png")
    dest = tmp_path / "a.jxl"
    encode_jxl(source, dest)
    assert probe_dimensions(dest) == (32, 24)
    with Image.open(dest) as image:
        image.load()
        assert image.getpixel((1, 1)) == (200, 100, 50)


def test_encode_converts_palette_to_rgb(tmp_path):
    source = tmp_path / "p.png"
    Image.new("P", (8, 8)).save(source)
    dest = tmp_path / "p.jxl"
    encode_jxl(source, dest)
    with Image.open(dest) as image:
        assert image.mode in {"RGB", "RGBA"}
