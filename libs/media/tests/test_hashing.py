import hashlib
from pathlib import Path

from PIL import Image

from media.hashing import perceptual_hash, sha256_file


def make_image(path: Path, pattern: bool = False) -> Path:
    image = Image.new("L", (32, 32), 0)
    if pattern:
        for x in range(0, 32, 2):
            for y in range(32):
                image.putpixel((x, y), 255)
    image.save(path)
    return path


def test_sha256_is_stable(tmp_path):
    target = tmp_path / "a"
    target.write_bytes(b"x")
    assert sha256_file(target) == hashlib.sha256(b"x").hexdigest()


def test_perceptual_hash_is_stable(tmp_path):
    first = make_image(tmp_path / "a.png")
    second = make_image(tmp_path / "b.png")
    assert perceptual_hash(first) == perceptual_hash(second)
    assert len(perceptual_hash(first)) == 16


def test_perceptual_hash_separates_patterns(tmp_path):
    assert perceptual_hash(make_image(tmp_path / "solid.png")) != perceptual_hash(
        make_image(tmp_path / "pattern.png", pattern=True)
    )
