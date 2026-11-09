"""Library ordering: newest first, regardless of entity kind."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime

from .scan import Entity


def _parse(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _added_date(entity: Entity) -> date | None:
    try:
        files = [
            path.stat().st_mtime
            for path in entity.path.rglob("*")
            if path.is_file() and not path.is_symlink() and not path.name.startswith(".")
        ]
        stamp = min(files) if files else entity.path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(stamp, tz=UTC).date()


def entity_date(entity: Entity) -> date | None:
    metadata = entity.metadata
    if entity.kind == "movie" and metadata is not None:
        value = _parse(metadata.release_date)
    elif entity.kind == "series" and metadata is not None:
        value = _parse(metadata.last_release_date or metadata.first_release_date)
    else:
        value = None
    return value or _added_date(entity)


def _key(entity: Entity) -> tuple[bool, int, str, str]:
    value = entity_date(entity)
    return (
        value is None,
        -value.toordinal() if value is not None else 0,
        entity.title.casefold(),
        str(entity.path),
    )


def sort_entities(entities: Iterable[Entity]) -> list[Entity]:
    return sorted(entities, key=_key)
