import json
import logging
from scripts.support.credentials import mask_user_id
from datetime import datetime
from pathlib import Path


class CacheStore:
    FETCH_STAGES = ("none", "balance", "yearly", "monthly", "daily", "tou", "persist", "billing", "complete")

    def __init__(self, cache_file: Path):
        self.cache_file = cache_file

    def load(self) -> dict:
        if not self.cache_file.exists():
            return {}
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logging.warning("Failed to load cache file %s: %s", self.cache_file, exc)
            return {}

    def save(self, data: dict) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.cache_file.with_suffix(".tmp")
            temp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            temp_path.replace(self.cache_file)
            logging.debug("Saved data to cache file: %s", self.cache_file)
        except Exception as exc:
            logging.error("Failed to save cache file %s: %s", self.cache_file, exc)

    def _ensure_entry(self, data: dict, user_id: str) -> dict:
        entry = data.get(user_id)
        if not isinstance(entry, dict):
            entry = {}
            data[user_id] = entry
        entry.setdefault("data", {})
        entry.setdefault("progress", {})
        entry["progress"].setdefault("stage", "none")
        return entry

    def update_progress(self, user_id: str, **progress_fields) -> None:
        data = self.load()
        entry = self._ensure_entry(data, user_id)
        entry["progress"].update(progress_fields)
        entry["progress"]["updated_at"] = datetime.now().isoformat()
        self.save(data)

    def update_progress_stage(self, user_id: str, stage: str, fetch_date: str | None = None) -> None:
        if stage not in self.FETCH_STAGES:
            raise ValueError(f"Unsupported fetch stage: {stage}")
        fields = {"stage": stage}
        if fetch_date is not None:
            fields["fetch_date"] = fetch_date
        self.update_progress(user_id, **fields)

    def get_progress(self, user_id: str) -> dict:
        data = self.load()
        entry = self._ensure_entry(data, user_id)
        return entry.get("progress", {})

    def save_partial_data(self, user_id: str, **fields) -> None:
        data = self.load()
        entry = self._ensure_entry(data, user_id)
        current = entry.get("data", {})
        current.update(fields)
        current["timestamp"] = datetime.now().isoformat()
        entry["data"] = current
        self.save(data)

    def get_cached_user_data(self, user_id: str) -> dict:
        data = self.load()
        entry = self._ensure_entry(data, user_id)
        return entry.get("data", {})

    @staticmethod
    def is_progress_complete(progress: dict) -> bool:
        return isinstance(progress, dict) and progress.get("stage") == "complete"

    def should_skip_startup_fetch(self) -> bool:
        data = self.load()
        if not data:
            logging.info("Startup fetch cannot be skipped because cache is empty.")
            return False

        today = datetime.now().strftime("%Y-%m-%d")
        has_user_data = False
        for user_id, entry in data.items():
            if not isinstance(entry, dict):
                logging.info("Startup fetch cannot be skipped because cache entry for %s is invalid.", mask_user_id(user_id))
                return False

            user_data = entry.get("data", {})
            progress = entry.get("progress", {})
            if not user_data:
                logging.info("Startup fetch cannot be skipped because cache entry for %s has no data.", mask_user_id(user_id))
                return False

            has_user_data = True
            if progress.get("fetch_date") != today:
                logging.info(
                    "Startup fetch cannot be skipped because cache entry for %s is stale: fetch_date=%s today=%s",
                    user_id,
                    progress.get("fetch_date"),
                    today,
                )
                return False

            if not self.is_progress_complete(progress):
                logging.info(
                    "Startup fetch cannot be skipped because cache entry for %s is incomplete: progress=%s",
                    user_id,
                    progress,
                )
                return False

        if not has_user_data:
            logging.info("Startup fetch cannot be skipped because cache has no user data.")
            return False
        return True
