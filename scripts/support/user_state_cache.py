import logging
import os

from scripts.support.cache_store import CacheStore
from scripts.support.credentials import mask_user_id
from scripts.support.user_state import UserStateSnapshot


class UserStateCache:
    """Typed boundary for the user state stored in the runtime cache file."""

    def __init__(self, cache_store: CacheStore):
        self.cache_store = cache_store

    def save_snapshot(self, user_id: str, snapshot: UserStateSnapshot) -> None:
        data = self.cache_store.load()
        entry = data.get(user_id) if isinstance(data.get(user_id), dict) else {}
        if not entry:
            entry = {"data": {}, "progress": {"stage": "none"}}
            data[user_id] = entry
        current_data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
        current_data.update(snapshot.to_cache_data())
        entry["data"] = current_data
        self.cache_store.save(data)

    def iter_snapshots(self):
        cache_file = self.cache_store.cache_file
        abs_cache_file = os.path.abspath(cache_file)
        if not os.path.exists(cache_file):
            logging.info("No cache file found at %s, skipping republish.", abs_cache_file)
            return

        data = self.cache_store.load()
        logging.info("Loaded cache file %s with %s user entries.", cache_file, len(data))
        for user_id, values in data.items():
            logging.info("Republishing cached data for user %s", mask_user_id(user_id))
            if not isinstance(values, dict):
                logging.warning(
                    "Skip invalid cache entry for user %s: entry_type=%s",
                    mask_user_id(user_id),
                    type(values).__name__,
                )
                continue
            user_data = values.get("data", {})
            if not any(key in user_data for key in UserStateSnapshot.UPDATE_KEYS):
                continue
            yield user_id, UserStateSnapshot.from_cache_data(user_data)
