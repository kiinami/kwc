# Constants for the KWC Selector app
from pathlib import Path
from PIL import ExifTags

# Thumbnail and UI sizes
THUMBNAIL_WIDTH = 160
THUMBNAIL_HEIGHT = 100
CROSSFADE_DURATION = 200  # milliseconds
SCROLL_ANIMATION_DURATION = 300  # milliseconds
SCROLL_ANIMATION_STEPS = 30
LAZY_LOAD_BUFFER = 200  # pixels

# EXIF tag for hash
HASH_EXIF_TAG = None
for k, v in ExifTags.TAGS.items():
    if v == 'UserComment':
        HASH_EXIF_TAG = k
        break
HASH_EXIF_PREFIX = b'kwc_hash:'
