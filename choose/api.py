from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings

from extract.utils import render_pattern
from kwc.utils.files import safe_remove, safe_rename

from .constants import SEASON_EPISODE_PATTERN
from .models import FolderProgress, ImageDecision
from .utils import (
    get_folder_path,
    list_image_files,
    parse_season_episode,
    parse_title_year_from_folder,
    parse_version_suffix,
    strip_version_suffix,
    add_version_suffix,
    validate_folder_name,
    wallpapers_root,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class DecisionPayload:
    filename: str = ""
    decision: str = ""


@dataclass(slots=True, frozen=True)
class ApplyResult:
    payload: dict[str, Any]
    status: int = 200


class APIError(Exception):
    """Raised when API helper processing should translate to an HTTP error."""

    def __init__(self, code: str, status: int = 400, detail: str | None = None) -> None:
        self.code = code
        self.status = status
        self.detail = detail
        message = detail or code
        super().__init__(message)


SEASON_EPISODE_RE = re.compile(SEASON_EPISODE_PATTERN, re.IGNORECASE)


def parse_decision_request(body: bytes) -> DecisionPayload:
    """Decode and sanitise a decision payload from raw request bytes."""

    if not body:
        data: dict[str, Any] = {}
    else:
        try:
            decoded = body.decode("utf-8")
        except UnicodeDecodeError as exc:  # pragma: no cover - defensive
            logger.debug("Failed to decode decision payload: %s", exc)
            raise APIError("invalid_json", 400) from exc

        if not decoded.strip():
            data = {}
        else:
            try:
                data = json.loads(decoded)
            except json.JSONDecodeError as exc:
                logger.debug("Failed to parse decision payload %r: %s", decoded, exc)
                raise APIError("invalid_json", 400) from exc

    if not isinstance(data, dict):
        raise APIError("invalid_json", 400)

    filename = str(data.get("filename", "")).strip()
    decision = str(data.get("decision", "")).strip()

    return DecisionPayload(filename=filename, decision=decision)


def apply_decisions(folder: str, payload: DecisionPayload) -> ApplyResult:
    """Apply queued decisions for a folder: move kept images to wallpapers folder, delete discarded ones.
    
    This works with the extraction staging area (extract_root) and moves kept images
    to the final wallpapers directory with proper sequential naming.
    """

    try:
        safe_name = validate_folder_name(folder)
    except ValueError as exc:
        raise APIError("invalid_folder", 400, str(exc)) from exc

    # Source: extraction staging area
    from .utils import extract_root
    extract_path = extract_root()
    
    try:
        source_folder = get_folder_path(safe_name, extract_path)
    except FileNotFoundError as exc:
        raise APIError("not_found", 404, str(exc)) from exc

    try:
        files = list_image_files(source_folder)
    except PermissionError as exc:
        logger.warning("Permission denied scanning folder %s: %s", safe_name, exc)
        raise APIError("permission_denied", 403, str(exc)) from exc

    decisions = list(
        ImageDecision.objects.filter(folder=safe_name).order_by("decided_at", "filename")
    )
    decision_map = {d.filename: d.decision for d in decisions}

    # Separate files into keep and delete
    to_delete = [name for name in files if decision_map.get(name) == ImageDecision.DECISION_DELETE]
    to_keep = [name for name in files if decision_map.get(name) == ImageDecision.DECISION_KEEP]
    # Undecided images are treated as keep
    undecided = [name for name in files if name not in to_delete and name not in to_keep]
    to_keep.extend(undecided)
    
    # Parse folder name to extract title, optional year, and season/episode
    # Examples: "Title", "Title (2024)", "Title S01", "Title S01E03", "Title E03"
    season, episode = parse_season_episode(safe_name)

    # Parse title and optional year first so that "Movie (2024)" -> ("Movie", 2024)
    title, parsed_year = parse_title_year_from_folder(safe_name)

    # Remove season/episode markers from the title if present
    if season or episode:
        pattern = r'\s+S\d+|\s+E[A-Z0-9]+|\s+S\d+E[A-Z0-9]+'
        title = re.sub(pattern, '', title, flags=re.IGNORECASE).strip()
    
    # Determine target folder in wallpapers directory
    # Use EXTRACT_FOLDER_PATTERN to create the folder name (title with optional year)
    wallpapers_path = wallpapers_root()
    
    # Try to find existing folder with matching title
    target_folder_name = None
    year_for_pattern = None
    
    if wallpapers_path.exists():
        for entry in wallpapers_path.iterdir():
            if not entry.is_dir() or entry.name.startswith('.'):
                continue
            
            folder_title, folder_year = parse_title_year_from_folder(entry.name)
            if folder_title == title:
                target_folder_name = entry.name
                year_for_pattern = folder_year
                break
    
    # If no existing folder found, create new one (title without year by default)
    if not target_folder_name:
        target_folder_name = title
    
    target_folder = wallpapers_path / target_folder_name
    target_folder.mkdir(parents=True, exist_ok=True)
    
    # Delete discarded images
    delete_errors: list[str] = []
    for name in to_delete:
        path = source_folder / name
        try:
            if path.exists() and path.is_file():
                safe_remove(path)
        except (OSError, IsADirectoryError) as exc:
            logger.warning("Failed to delete %s/%s: %s", safe_name, name, exc)
            delete_errors.append(f"{name}: {exc}")
    
    # Build suffix map and group files by their base name (without suffix)
    suffix_map: dict[str, str] = {}
    base_name_map: dict[str, str] = {}
    
    for name in to_keep:
        valid_suffix, invalid_suffix = parse_version_suffix(name)
        if valid_suffix:
            suffix_map[name] = valid_suffix
            base_name_map[name] = strip_version_suffix(name)
        else:
            suffix_map[name] = ""
            base_name_map[name] = name
    
    # Find highest existing counter in target folder for this season/episode
    pattern = settings.EXTRACT_IMAGE_PATTERN
    existing_files = list_image_files(target_folder) if target_folder.exists() else []
    
    # Parse existing files to find highest counter for matching season/episode
    counters: dict[tuple[str, str], int] = {}
    for existing_name in existing_files:
        base_name = base_name_map.get(existing_name, strip_version_suffix(existing_name))
        base_stem = os.path.splitext(base_name)[0]
        
        match = SEASON_EPISODE_RE.search(base_stem)
        file_season = match.group("season") if match else ""
        file_episode = (match.group("episode") or match.group("ep_only") or "") if match else ""
        
        # Extract counter
        counter_match = re.search(r'(\d+)$', base_stem)
        if counter_match:
            try:
                counter = int(counter_match.group(1))
                key = (file_season, file_episode)
                counters[key] = max(counters.get(key, 0), counter)
            except ValueError:
                pass
    
    # Move and rename kept images
    move_errors: list[str] = []
    moved_count = 0
    
    # Track which base names we've already processed
    base_to_counter: dict[tuple[tuple[str, str], str], int] = {}
    
    for name in to_keep:
        src = source_folder / name
        if not src.exists():
            continue
        
        # Parse season/episode from filename
        base_name_for_parsing = base_name_map.get(name, name)
        base_stem = os.path.splitext(base_name_for_parsing)[0]
        
        match = SEASON_EPISODE_RE.search(base_stem)
        file_season = match.group("season") if match else ""
        file_episode = (match.group("episode") or match.group("ep_only") or "") if match else ""
        key = (file_season, file_episode)
        
        # Check if we've already assigned a counter to this base image
        lookup_key = (key, base_name_for_parsing)
        if lookup_key in base_to_counter:
            # Reuse the same counter for this version
            counter = base_to_counter[lookup_key]
        else:
            # New base image - prefer to reuse the existing highest counter if present
            # This allows creating a _dup fallback when an existing file uses that counter,
            # and then increment for subsequent images.
            current_high = counters.get(key, 0)
            counter = current_high if current_high > 0 else 1
            # Advance the stored counter so the next new base gets the next number
            counters[key] = counter + 1
            base_to_counter[lookup_key] = counter
        
        # Build new filename
        values = {
            "title": title,
            "base_title": title,
            "year": year_for_pattern or "",
            "season": int(file_season) if file_season and file_season.isdigit() else file_season,
            "episode": int(file_episode) if file_episode and file_episode.isdigit() else file_episode,
            "counter": counter,
        }
        
        try:
            new_name = render_pattern(pattern, values)
        except Exception as e:
            logger.warning(f"Failed to render pattern for {name}: {e}")
            new_name = f"{title}_{counter:04d}.jpg"
        
        # Re-apply version suffix if the original had one
        if name in suffix_map and suffix_map[name]:
            new_name = add_version_suffix(new_name, suffix_map[name])
        
        dest = target_folder / new_name
        
        # Handle collisions
        if dest.exists():
            stem, ext = os.path.splitext(new_name)
            collision_counter = 1
            while dest.exists():
                dest = target_folder / f"{stem}_dup{collision_counter}{ext}"
                collision_counter += 1
        
        try:
            import shutil
            shutil.move(str(src), str(dest))
            moved_count += 1
        except (OSError, IOError) as exc:
            logger.error("Move failed %s -> %s: %s", src, dest, exc)
            move_errors.append(f"{name} -> {dest.name}: {exc}")
    
    # Copy cover file if it exists in the source
    for cover_name in [".cover.jpg", ".cover.jpeg", ".cover.png", ".cover.webp"]:
        cover_src = source_folder / cover_name
        if cover_src.exists():
            cover_dest = target_folder / cover_name
            if not cover_dest.exists():
                try:
                    import shutil
                    shutil.copy2(str(cover_src), str(cover_dest))
                except Exception as e:
                    logger.warning(f"Failed to copy cover: {e}")
            break
    
    # Clean up: remove source folder if empty
    try:
        if not any(source_folder.iterdir()):
            source_folder.rmdir()
    except Exception as e:
        logger.warning(f"Failed to remove empty extraction folder {source_folder}: {e}")
    
    # Clear decisions and progress for this folder
    ImageDecision.objects.filter(folder=safe_name).delete()
    FolderProgress.objects.filter(folder=safe_name).delete()
    
    if move_errors:
        return ApplyResult(
            payload={
                "error": "move_failed",
                "details": move_errors,
                "delete_errors": delete_errors,
                "moved": moved_count,
            },
            status=500,
        )
    
    return ApplyResult(
        payload={
            "ok": True,
            "moved": moved_count,
            "deleted": len(to_delete),
            "delete_errors": delete_errors,
            "target_folder": target_folder_name,
        },
        status=200,
    )


def _cleanup_temporary_files(tmp_map: dict[Path, Path], *, restore: bool = False) -> None:
    """Ensure temporary files are cleaned up, optionally restoring originals."""

    for original, tmp in list(tmp_map.items()):
        if not tmp.exists():
            tmp_map.pop(original, None)
            continue
        try:
            if restore:
                safe_rename(tmp, original)
            else:
                safe_remove(tmp)
        except Exception as exc:  # pragma: no cover - best effort cleanup
            logger.warning("Failed cleaning temp file %s: %s", tmp, exc)
        finally:
            tmp_map.pop(original, None)
