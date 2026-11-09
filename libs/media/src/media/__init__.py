"""Image format, hash, and metadata helpers."""

from PIL import Image

# The archive is trusted, server-side content. Imports enforce an explicit pixel budget;
# Pillow's generic bomb guard is lower than real 16K/panorama assets and fires first.
Image.MAX_IMAGE_PIXELS = None
