from __future__ import annotations

from collections.abc import Callable


def resolve_user_ids(local_user_ids: list[str] | None, page_loader: Callable[[], list[str]]) -> list[str]:
    if local_user_ids:
        return list(local_user_ids)
    return page_loader()
