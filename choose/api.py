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
    """Apply queued decisions for a folder, mirroring legacy behaviour."""

    try:
        safe_name = validate_folder_name(folder)
    except ValueError as exc:
        raise APIError("invalid_folder", 400, str(exc)) from exc

    root_path = wallpapers_root()

    try:
        target = get_folder_path(safe_name, root_path)
    except FileNotFoundError as exc:
        raise APIError("not_found", 404, str(exc)) from exc

    try:
        files = list_image_files(target)
    except PermissionError as exc:
        logger.warning("Permission denied scanning folder %s: %s", safe_name, exc)
        raise APIError("permission_denied", 403, str(exc)) from exc

    decisions = list(
        ImageDecision.objects.filter(folder=safe_name).order_by("decided_at", "filename")
    )
    decision_map = {d.filename: d.decision for d in decisions}

    indices_by_name = {name: idx for idx, name in enumerate(files)}
    previous_progress = FolderProgress.objects.filter(folder=safe_name).first()
    prev_keep_count = previous_progress.keep_count if previous_progress else 0

    to_delete = [name for name in files if decision_map.get(name) == ImageDecision.DECISION_DELETE]
    remaining_names = [name for name in files if name not in to_delete]

    ordered_decided_keeps: list[str] = []
    seen_keeps: set[str] = set()
    for decision in decisions:
        if decision.decision != ImageDecision.DECISION_KEEP:
            continue
        name = decision.filename
        if name in seen_keeps or name not in indices_by_name or name in to_delete:
            continue
        ordered_decided_keeps.append(name)
        seen_keeps.add(name)

    delete_errors: list[str] = []
    for name in to_delete:
        path = target / name
        try:
            if path.exists() and path.is_file():
                safe_remove(path)
        except (OSError, IsADirectoryError) as exc:
            logger.warning("Failed to delete %s/%s: %s", safe_name, name, exc)
            delete_errors.append(f"{name}: {exc}")

    base_title, parsed_year = parse_title_year_from_folder(safe_name)
    pattern = settings.EXTRACT_IMAGE_PATTERN

    tmp_map: dict[Path, Path] = {}

    undecided_keeps = [name for name in remaining_names if name not in seen_keeps]

    # Build suffix map and group files by their base name (without suffix)
    suffix_map: dict[str, str] = {}
    base_name_map: dict[str, str] = {}  # Maps filename to its base (without suffix)
    
    for name in files:
        valid_suffix, invalid_suffix = parse_version_suffix(name)
        # If valid suffix exists, store it
        if valid_suffix:
            suffix_map[name] = valid_suffix
            base_name_map[name] = strip_version_suffix(name)
        else:
            # No suffix or invalid suffix - treat as base
            suffix_map[name] = ""
            base_name_map[name] = name

    tmp_counter = 0
    plans_decided: list[tuple[Path, Path]] = []
    for name in ordered_decided_keeps:
        tmp_counter += 1
        src = target / name
        tmp = target / f".{tmp_counter:04d}.renametmp.{os.getpid()}_{tmp_counter}{src.suffix.lower()}"
        try:
            if src.exists():
                safe_rename(src, tmp)
                tmp_map[src] = tmp
                plans_decided.append((src, tmp))
        except (FileNotFoundError, OSError) as exc:
            logger.error("Temp rename failed for %s/%s: %s", safe_name, src.name, exc)
            _cleanup_temporary_files(tmp_map, restore=True)
            raise APIError("temp_rename_failed", 500, str(exc)) from exc

    preview_counters: dict[tuple[str, str], int] = {}
    keep_dest_names: set[str] = set()
    # Track which base names we've already assigned counters to (for preview)
    preview_assigned_bases: dict[tuple[str, str], set[str]] = {}
    
    for original_src, _tmp in plans_decided:
        original_name = original_src.name
        base_name_for_parsing = base_name_map.get(original_name, original_name)
        base_stem = os.path.splitext(base_name_for_parsing)[0]
        
        match = SEASON_EPISODE_RE.search(base_stem)
        season = match.group("season") if match else ""
        # Episode can be in either "episode" group (when season present) or "ep_only" group
        episode = (match.group("episode") or match.group("ep_only") or "") if match else ""
        key = (season, episode)
        
        # Only increment counter if this is a new base image (not a version of one we've seen)
        if key not in preview_assigned_bases:
            preview_assigned_bases[key] = set()
        
        if base_name_for_parsing not in preview_assigned_bases[key]:
            current = preview_counters.get(key, 0) + 1
            preview_counters[key] = current
            preview_assigned_bases[key].add(base_name_for_parsing)
        else:
            # This is a version of an image we've already counted
            current = preview_counters[key]
        
        values = {
            "title": base_title,
            "base_title": base_title,
            "year": parsed_year or "",
            "season": int(season) if season and season.isdigit() else season,
            "episode": int(episode) if episode and episode.isdigit() else episode,
            "counter": current,
        }
        new_base_name = render_pattern(pattern, values)
        # Add both base and versioned names to the set
        keep_dest_names.add(new_base_name)
        if original_name in suffix_map and suffix_map[original_name]:
            versioned_name = add_version_suffix(new_base_name, suffix_map[original_name])
            keep_dest_names.add(versioned_name)

    deferred_names = [name for name in undecided_keeps if name in keep_dest_names]
    other_undecided = [name for name in undecided_keeps if name not in keep_dest_names]

    plans_other: list[tuple[Path, Path]] = []
    for name in other_undecided:
        tmp_counter += 1
        src = target / name
        tmp = target / f".{tmp_counter:04d}.renametmp.{os.getpid()}_{tmp_counter}{src.suffix.lower()}"
        try:
            if src.exists():
                safe_rename(src, tmp)
                tmp_map[src] = tmp
                plans_other.append((src, tmp))
        except (FileNotFoundError, OSError) as exc:
            logger.error("Temp rename failed for %s/%s: %s", safe_name, src.name, exc)
            _cleanup_temporary_files(tmp_map, restore=True)
            raise APIError("temp_rename_failed", 500, str(exc)) from exc

    rename_errors: list[str] = []
    counters: dict[tuple[str, str], int] = {}
    final_keep_names: list[str] = []
    # Track which base names we've already assigned counters to (for actual renames)
    assigned_bases: dict[tuple[str, str], set[str]] = {}
    # Map from base name to the counter it was assigned
    base_to_counter: dict[tuple[tuple[str, str], str], int] = {}

    def _finalise_renames(plans: list[tuple[Path, Path]]) -> bool:
        for original_src, tmp in plans:
            tmp_path = tmp_map.get(original_src)
            if tmp_path is None or not tmp_path.exists():
                continue

            # Strip version suffix from original filename before parsing
            original_name = original_src.name
            base_name_for_parsing = base_name_map.get(original_name, original_name)
            base_stem = os.path.splitext(base_name_for_parsing)[0]
            
            match = SEASON_EPISODE_RE.search(base_stem)
            season = match.group("season") if match else ""
            # Episode can be in either "episode" group (when season present) or "ep_only" group
            episode = (match.group("episode") or match.group("ep_only") or "") if match else ""
            key = (season, episode)
            
            # Check if we've already assigned a counter to this base image
            if key not in assigned_bases:
                assigned_bases[key] = set()
            
            lookup_key = (key, base_name_for_parsing)
            if lookup_key in base_to_counter:
                # Reuse the same counter for this version
                current = base_to_counter[lookup_key]
            else:
                # New base image - assign new counter
                current = counters.get(key, 0) + 1
                counters[key] = current
                assigned_bases[key].add(base_name_for_parsing)
                base_to_counter[lookup_key] = current

            values = {
                "title": base_title,
                "base_title": base_title,
                "year": parsed_year or "",
                "season": int(season) if season and season.isdigit() else season,
                "episode": int(episode) if episode and episode.isdigit() else episode,
                "counter": current,
            }

            new_name = render_pattern(pattern, values)
            
            # Re-apply version suffix if the original had one
            if original_name in suffix_map and suffix_map[original_name]:
                new_name = add_version_suffix(new_name, suffix_map[original_name])
            
            dest = target / new_name

            try:
                if dest.exists():
                    try:
                        safe_remove(dest)
                    except (OSError, IsADirectoryError):
                        stem, ext = os.path.splitext(new_name)
                        # Build fallback suffix based on what info we have
                        if season and episode:
                            fallback_suffix = f" S{season}E{episode} #{current}"
                        elif season:
                            fallback_suffix = f" S{season} #{current}"
                        elif episode:
                            fallback_suffix = f" E{episode} #{current}"
                        else:
                            fallback_suffix = f" #{current}"
                        dest = target / f"{stem}{fallback_suffix}{ext}"
                safe_rename(tmp_path, dest)
                tmp_map.pop(original_src, None)
                final_keep_names.append(dest.name)
            except (FileNotFoundError, OSError) as exc:
                logger.error("Rename failed %s -> %s: %s", tmp, dest, exc)
                rename_errors.append(f"{original_src.name} -> {dest.name}: {exc}")
                return False
        return True

    if not _finalise_renames(plans_decided):
        _cleanup_temporary_files(tmp_map, restore=True)
        return ApplyResult(
            payload={
                "error": "rename_failed",
                "details": rename_errors,
                "delete_errors": delete_errors,
            },
            status=500,
        )

    if not _finalise_renames(plans_other):
        _cleanup_temporary_files(tmp_map, restore=True)
        return ApplyResult(
            payload={
                "error": "rename_failed",
                "details": rename_errors,
                "delete_errors": delete_errors,
            },
            status=500,
        )

    plans_deferred: list[tuple[Path, Path]] = []
    for name in deferred_names:
        tmp_counter += 1
        src = target / name
        tmp = target / f".{tmp_counter:04d}.renametmp.{os.getpid()}_{tmp_counter}{src.suffix.lower()}"
        try:
            if src.exists():
                safe_rename(src, tmp)
                tmp_map[src] = tmp
                plans_deferred.append((src, tmp))
        except (FileNotFoundError, OSError) as exc:
            logger.error("Temp rename failed for %s/%s: %s", safe_name, src.name, exc)
            _cleanup_temporary_files(tmp_map, restore=True)
            raise APIError("temp_rename_failed", 500, str(exc)) from exc

    if not _finalise_renames(plans_deferred):
        _cleanup_temporary_files(tmp_map, restore=True)
        return ApplyResult(
            payload={
                "error": "rename_failed",
                "details": rename_errors,
                "delete_errors": delete_errors,
            },
            status=500,
        )

    if rename_errors:
        _cleanup_temporary_files(tmp_map, restore=True)
        return ApplyResult(
            payload={
                "error": "rename_failed",
                "details": rename_errors,
                "delete_errors": delete_errors,
            },
            status=500,
        )

    _cleanup_temporary_files(tmp_map)

    remaining_prev_keep_count = sum(1 for name in files[:prev_keep_count] if name not in to_delete)
    keep_names_beyond_prev = {
        name
        for name, decision in decision_map.items()
        if decision == ImageDecision.DECISION_KEEP and indices_by_name.get(name, len(files)) >= prev_keep_count
    }
    new_processed_count = remaining_prev_keep_count + len(keep_names_beyond_prev)
    if new_processed_count > len(final_keep_names):
        new_processed_count = len(final_keep_names)

    anchor_name = ""
    if new_processed_count > 0 and final_keep_names:
        anchor_index = min(new_processed_count - 1, len(final_keep_names) - 1)
        anchor_name = final_keep_names[anchor_index]

    last_original_name = (
        decisions[-1].filename
        if decisions
        else (previous_progress.last_classified_original if previous_progress else "")
    )

    FolderProgress.objects.update_or_create(
        folder=safe_name,
        defaults={
            "last_classified_name": anchor_name,
            "last_classified_original": last_original_name,
            "keep_count": new_processed_count,
        },
    )

    ImageDecision.objects.filter(folder=safe_name).delete()

    keep_decision_count = len(ordered_decided_keeps)
    kept_total = keep_decision_count if keep_decision_count else len(remaining_names)

    return ApplyResult(
        payload={
            "ok": True,
            "deleted": len(to_delete),
            "kept": kept_total,
            "delete_errors": delete_errors,
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
