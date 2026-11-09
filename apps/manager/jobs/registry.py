from collections.abc import Callable
from typing import TYPE_CHECKING

from .models import Job

if TYPE_CHECKING:
    from .worker import JobContext

Handler = Callable[[Job, "JobContext"], dict | None]

_HANDLERS: dict[str, Handler] = {}


def register(kind: str) -> Callable[[Handler], Handler]:
    def decorator(handler: Handler) -> Handler:
        _HANDLERS[kind] = handler
        return handler

    return decorator


def get_handler(kind: str) -> Handler | None:
    return _HANDLERS.get(kind)
