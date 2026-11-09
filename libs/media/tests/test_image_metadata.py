import json
from pathlib import Path

from PIL import Image

from media.jxl import encode_jxl
from media.metadata import ImageMetadata, read_image_metadata, write_image_metadata


def make_jxl(path: Path, *, exif: Image.Exif | None = None) -> Path:
    png = path.with_suffix(".png")
    image = Image.new("RGB", (16, 16), (1, 2, 3))
    image.putpixel((1, 1), (200, 100, 50))
    image.save(png)
    if exif is None:
        encode_jxl(png, path)
    else:
        image.save(path, format="JXL", lossless=True, exif=exif.tobytes())
    return path


def test_round_trip(tmp_path):
    image = make_jxl(tmp_path / "a.jxl")
    write_image_metadata(image, ImageMetadata(source_sha256="abc", timestamp=12.5, generator="import"))
    got = read_image_metadata(image)
    assert got.source_sha256 == "abc"
    assert got.timestamp == 12.5
    assert got.generator == "import"


def test_write_preserves_pixels(tmp_path):
    image = make_jxl(tmp_path / "a.jxl")
    write_image_metadata(image, ImageMetadata(copyright="(c) Studio"))
    with Image.open(image) as reopened:
        reopened.load()
        assert reopened.getpixel((1, 1)) == (200, 100, 50)


def test_missing_comment_returns_empty(tmp_path):
    image = make_jxl(tmp_path / "a.jxl")
    assert read_image_metadata(image) == ImageMetadata()


def test_invalid_comment_returns_empty(tmp_path):
    exif = Image.Exif()
    exif[0x9286] = b"ASCII\0\0\0not json"
    image = make_jxl(tmp_path / "a.jxl", exif=exif)
    assert read_image_metadata(image) == ImageMetadata()


def test_preserves_other_exif_tags(tmp_path):
    exif = Image.Exif()
    exif[0x010F] = "KWC"
    image = make_jxl(tmp_path / "a.jxl", exif=exif)
    write_image_metadata(image, ImageMetadata(copyright="(c) Studio"))
    with Image.open(image) as reopened:
        got = Image.Exif()
        got.load(reopened.info["exif"])
    assert got.get(0x010F) == "KWC"


def test_unknown_keys_survive(tmp_path):
    exif = Image.Exif()
    exif[0x9286] = b"ASCII\0\0\0" + json.dumps({"custom": "keep"}).encode()
    image = make_jxl(tmp_path / "a.jxl", exif=exif)
    assert read_image_metadata(image).extra == {"custom": "keep"}
