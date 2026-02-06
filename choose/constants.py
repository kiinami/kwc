"""Constants used across the choose app."""

# Supported image file extensions (lowercase)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Season/episode pattern for parsing filenames
# Supports: S01E02 (season+episode), S01 (season only), E02 (episode only)
# Uses word boundaries to avoid false matches like "frame01"
SEASON_EPISODE_PATTERN = (
    r"\b(?:S(?P<season>\d{1,3})(?:E(?P<episode>[A-Za-z0-9]{1,6}))?|E(?P<ep_only>[A-Za-z0-9]{1,6}))\b"
)

# Thumbnail configuration
THUMB_MAX_DIMENSION = 4096
THUMB_CACHE_SIZE = 256
