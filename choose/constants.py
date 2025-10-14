"""Constants used across the choose app."""

# Supported image file extensions (lowercase)
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}

# Season/episode pattern for parsing filenames like "S01E02"
SEASON_EPISODE_PATTERN = r"S(?P<season>\d{1,3})E(?P<episode>[A-Za-z0-9]{1,6})"

# Thumbnail configuration
THUMB_MAX_DIMENSION = 4096
THUMB_CACHE_SIZE = 256
