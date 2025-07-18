# Standard library imports
from pathlib import Path
import os

# Third-party imports
import imagehash
from PIL import Image, ExifTags

# Local application imports
from .constants import HASH_EXIF_TAG, HASH_EXIF_PREFIX


def get_or_compute_hash(img_path: Path) -> str:
    """Get hash from EXIF or compute and store it if missing.

    Args:
        img_path: Path to the image file.

    Returns:
        The perceptual hash as a hex string.
    """
    try:
        with Image.open(img_path) as im:
            exif = im.getexif()
            hashval = None
            if HASH_EXIF_TAG and exif and HASH_EXIF_TAG in exif:
                val = exif[HASH_EXIF_TAG]
                if isinstance(val, bytes) and val.startswith(HASH_EXIF_PREFIX):
                    hashval = val[len(HASH_EXIF_PREFIX):].decode('utf-8')
                elif isinstance(val, str) and val.startswith('kwc_hash:'):
                    hashval = val.split(':', 1)[1]
            if not hashval:
                hashval = str(imagehash.phash(im))
                if HASH_EXIF_TAG:
                    exif[HASH_EXIF_TAG] = HASH_EXIF_PREFIX + hashval.encode('utf-8')
                    # im.save(img_path, exif=exif)
            return hashval
    except Exception as e:
        print(f"Error hashing {img_path}: {e}")
        return '0'*16


def group_images_by_hash(all_images: list[Path], image_hashes: dict, max_distance: int = 5) -> list[list[Path]]:
    """Group adjacent images by perceptual hash distance."""
    image_groups = []
    if not all_images:
        return image_groups
    group = [all_images[0]]
    prev_hash = image_hashes[all_images[0]]
    for img in all_images[1:]:
        h = image_hashes[img]
        dist = imagehash.hex_to_hash(prev_hash) - imagehash.hex_to_hash(h)
        if dist <= max_distance:
            group.append(img)
        else:
            image_groups.append(group)
            group = [img]
        prev_hash = h
    if group:
        image_groups.append(group)
    return image_groups


def get_all_images(source_dir: Path, selected_dir: Path, discarded_dir: Path) -> list[Path]:
    """Get all .jpg images from the three directories, sorted by numeric suffix."""
    images = list(source_dir.glob('*.jpg'))
    images += list(selected_dir.glob('*.jpg'))
    images += list(discarded_dir.glob('*.jpg'))
    images = sorted(images, key=lambda x: int(x.stem.split('_')[-1]))
    return images
